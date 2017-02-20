from ..breakpoint import BreakpointPair, Breakpoint
from ..constants import CALL_METHOD, SVTYPE, PYSAM_READ_FLAGS, ORIENT
from ..bam.read import breakpoint_pos
from ..interval import Interval
from ..error import NotSpecifiedError
import itertools
import statistics
import math
from copy import copy as sys_copy


class EventCall(BreakpointPair):
    """
    class for holding evidence and the related calls since we can't freeze the evidence object
    directly without a lot of copying. Instead we use call objects which are basically
    just a reference to the evidence object and decisions on class, exact breakpoints, etc
    """
    def __init__(
        self,
        b1, b2,
        source_evidence,
        event_type,
        call_method,
        break2_call_method=None,
        contig=None,
        contig_alignment=None,
        untemplated_sequence=None
    ):
        """
        Args:
            evidence (Evidence): the evidence object we are calling based on
            event_type (SVTYPE): the type of structural variant
            breakpoint_pair (BreakpointPair): the breakpoint pair representing the exact breakpoints
            call_method (CALL_METHOD): the way the breakpoints were called
            contig (Contig): the contig used to call the breakpoints (if applicable)
        """
        if untemplated_sequence is None:
            untemplated_sequence = source_evidence.untemplated_sequence

        BreakpointPair.__init__(
            self, b1, b2,
            stranded=source_evidence.stranded and source_evidence.bam_cache.stranded,
            opposing_strands=source_evidence.opposing_strands,
            untemplated_sequence=untemplated_sequence,
            data=source_evidence.data
        )
        self.evidence = source_evidence
        self.event_type = SVTYPE.enforce(event_type)
        if event_type not in BreakpointPair.classify(source_evidence):
            raise ValueError(
                'event_type is not compatible with the evidence source allowable types', event_type, source_evidence)
        self.contig = contig
        self.call_method = None
        if contig:
            self.call_method = (CALL_METHOD.CONTIG, CALL_METHOD.CONTIG)
            if call_method or break2_call_method:
                raise AttributeError('contig overrides call method arguments')
        elif break2_call_method:
            self.call_method = (CALL_METHOD.enforce(call_method), CALL_METHOD.enforce(break2_call_method))
        else:
            self.call_method = (CALL_METHOD.enforce(call_method), CALL_METHOD.enforce(call_method))
        self.contig_alignment = contig_alignment

    def count_flanking_support(self):
        """
        counts the flanking read-pair support for the event called

        Returns:
            tuple of int and int and int:
            * (*int*) - the number of flanking read pairs
            * (*int*) - the median insert size
            * (*int*) - the standard deviation (from the median) of the insert size
        """
        support = set()

        fragment_sizes = []
        for read in itertools.chain.from_iterable(self.evidence.flanking_pairs):
            isize = abs(read.template_length)
            if (self.event_type == SVTYPE.INS and isize < exp_isize_range.start) \
                    or (self.event_type == SVTYPE.DEL and isize > exp_isize_range.end) \
                    or self.event_type not in [SVTYPE.DEL, SVTYPE.INS]:
                support.add(read.query_name)
                fragment_sizes.append(isize)

        if len(support) > 0:
            median = statistics.median(fragment_sizes)
            err = 0
            for insert in fragment_sizes:
                err += math.pow(insert - median, 2)
            err /= len(fragment_sizes)
            stdev = math.sqrt(err)
            return len(support), median, stdev
        else:
            return 0, 0, 0

    def count_split_read_support(self):
        """
        counts the split read support for the event called. split reads are only considered to
        be supporting the current call if they exactly match the breakpoint pair associated
        with this call

        Returns:
            tuple of int and int and int:
            * (*int*) - the number of split reads supporting the first breakpoint
            * (*int*) - the number of split reads supporting the second breakpoint
            * (*int*) - the number of split reads supporting the pairing of these breakpoints
        """
        support1 = set()
        realigns1 = set()
        support2 = set()
        realigns2 = set()

        for read in self.evidence.split_reads[0]:
            try:
                bpos = breakpoint_pos(read, self.break1.orient)
                if Interval.overlaps((bpos, bpos), self.break1):
                    support1.add(read.query_name)
                    if read.has_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT) and \
                            read.get_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT):
                        realigns1.add(read.query_name)
            except AttributeError:
                pass

        for read in self.evidence.split_reads[1]:
            try:
                bpos = breakpoint_pos(read, self.break2.orient)
                if Interval.overlaps((bpos, bpos), self.break2):
                    support2.add(read.query_name)
                    if read.has_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT) and \
                            read.get_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT):
                        realigns2.add(read.query_name)
            except AttributeError:
                pass

        return len(support1), len(realigns1), len(support2), len(realigns2), len(support1 & support2)

    def __hash__(self):
        raise NotImplementedError('this object type does not support hashing')

    def __eq__(self, other):
        object.__eq__(self, other)


def call_events(source_evidence, event_type):
    """
    use the associated evidence and event_types and split the current evidence object
    into more specific objects.

    Returns:
        :class:`list` of :class:`EventCall`: list of calls
    """
    if event_type not in source_evidence.putative_event_types():
        raise ValueError(
            'event_type is not compatible with the evidence object', event_type, source_evidence.putative_event_types())
    calls = []
    errors = set()
    # try calling by contigs
    calls.extend(_call_by_contigs(source_evidence, event_type))

    if len(calls) == 0:
        # try calling by split reads
        try:
            calls.extend(_call_by_supporting_reads(source_evidence, event_type))
        except UserWarning as err:
            errors.add(str(err))
    if len(calls) == 0 and len(errors) > 0:
        raise UserWarning(';'.join(sorted(list(errors))))
    elif len(calls) == 0:
        raise UserWarning('insufficient evidence to call events')
    return calls


def _call_by_contigs(ev, event_type):
    # resolve the overlap if multi-read alignment
    events = []
    for ctg in ev.contigs:
        for read1, read2 in ctg.alignments:
            try:
                bpp = BreakpointPair.call_breakpoint_pair(read1, read2)
            except UserWarning as err:
                continue
            if bpp.opposing_strands != ev.opposing_strands \
                    or (event_type == SVTYPE.INS and bpp.untemplated_sequence == '') \
                    or event_type not in BreakpointPair.classify(bpp):
                continue
            new_event = EventCall(
                bpp.break1,
                bpp.break2,
                ev,
                event_type,
                contig=ctg,
                alignment=(read1, read2),
                opposing_strands=bpp.opposing_strands,
                untemplated_sequence=bpp.untemplated_sequence
            )
            events.append(new_event)
    return events


def _call_by_flanking_pairs(ev, event_type, first_breakpoint_called=None, second_breakpoint_called=None):
    # for all flanking read pairs mark the farthest possible distance to the breakpoint
    # the start/end of the read on the breakpoint side
    first_positions = []
    second_positions = []
    if first_breakpoint_called and second_breakpoint_called:
        raise ValueError('do not bother calling when both breakpoints have already been called')

    flanking_count = 0
    for read, mate in ev.flanking_pairs:
        # check that the fragment size is reasonable
        fragment_size = ev.compute_fragment_size(read, mate)
        if event_type == SVTYPE.DEL:
            if fragment_size.end <= ev.max_expected_fragment_size:
                continue
        elif event_type == SVTYPE.INS:
            if fragment_size.start >= ev.min_expected_fragment_size:
                continue
        flanking_count += 1
        first_positions.extend([read.reference_start + 1, read.reference_end, mate.next_reference_start + 1])
        second_positions.extend([mate.reference_start + 1, mate.reference_end, read.next_reference_start + 1])

    if flanking_count < ev.min_flanking_pairs_resolution:
        raise AssertionError('insufficient coverage to call by flanking reads')

    cover1 = Interval(min(first_positions), max(first_positions))
    cover2 = Interval(min(second_positions), max(second_positions))

    print('first_positions', first_positions)
    print('second_positions', second_positions)
    print('first_breakpoint_called', first_breakpoint_called)
    print('second_breakpoint_called', second_breakpoint_called)
    print(cover1, cover2)
    if not ev.interchromosomal and Interval.overlaps(cover1, cover2):
        raise AssertionError('flanking read coverage overlaps. cannot call by flanking reads', cover1, cover2)
    if len(cover1) + ev.read_length * 2 > ev.max_expected_fragment_size or \
            len(cover2) + ev.read_length * 2 > ev.max_expected_fragment_size:
        raise AssertionError(
            'Cannot resolve by flanking reads. Coverage interval of flanking reads is larger than '
            'expected for normal variation. It is likely there are flanking reads for multiple events',
            cover1, cover2, ev.max_expected_fragment_size
        )
    print('cover1', cover1, len(cover1), 'cover2', cover2, len(cover2))
    print('ev.max_expected_fragment_size', ev.max_expected_fragment_size)
    print('ev.read_length', ev.read_length)

    if first_breakpoint_called is None:
        max_breakpoint_width = ev.max_expected_fragment_size - len(cover1) - ev.read_length * 2
        print('1 max_breakpoint_width', max_breakpoint_width)

        if ev.break1.orient == ORIENT.LEFT:
            end = cover1.end + max_breakpoint_width
            print(end)
            if not ev.interchromosomal:
                end = min([end, cover2.start - 1])
                print(end)
                if second_breakpoint_called:
                    end = min([end, second_breakpoint_called.end - 1])
                    print(end)
            try:
                first_breakpoint_called = Breakpoint(
                    ev.break1.chr,
                    cover1.end, end,
                    orient=ev.break1.orient,
                    strand=ev.break1.strand
                )
            except AttributeError:
                raise AssertionError(
                    'input breakpoint is incompatible with flanking coverage region', cover1, second_breakpoint_called)
        elif ev.break1.orient == ORIENT.RIGHT:
            first_breakpoint_called = Breakpoint(
                ev.break1.chr,
                max([cover1.start - max_breakpoint_width, 1]),
                max([cover1.start, 1]),
                orient=ev.break1.orient,
                strand=ev.break1.strand
            )
        else:
            raise NotSpecifiedError('Cannot call by flanking if orientation was not given')

    if second_breakpoint_called is None:
        max_breakpoint_width = ev.max_expected_fragment_size - len(cover2) - ev.read_length * 2
        print(ev.max_expected_fragment_size, len(cover2), ev.read_length * 2)
        print('2 max_breakpoint_width', max_breakpoint_width)

        if ev.break2.orient == ORIENT.LEFT:
            second_breakpoint_called = Breakpoint(
                ev.break2.chr,
                cover2.end,
                cover2.end + max_breakpoint_width,
                orient=ev.break2.orient,
                strand=ev.break2.strand
            )
        elif ev.break2.orient == ORIENT.RIGHT:
            start = max([cover2.start - max_breakpoint_width, 1])
            print('s2', start)
            if not ev.interchromosomal:
                start = max([start, cover1.end + 1])
                print('s2', start)
                if first_breakpoint_called:
                    start = max([start, first_breakpoint_called.start + 1])
                    print('s2', start)
            try:
                second_breakpoint_called = Breakpoint(
                    ev.break2.chr,
                    start,
                    cover2.start,
                    orient=ev.break2.orient,
                    strand=ev.break2.strand
                )
            except AttributeError:
                raise AssertionError(
                    'input breakpoint is incompatible with flanking coverage region', cover2, first_breakpoint_called)
        else:
            raise NotSpecifiedError('Cannot call by flanking if orientation was not given')
    return first_breakpoint_called, second_breakpoint_called


def _call_by_supporting_reads(ev, event_type):
    """
    use split read evidence to resolve bp-level calls for breakpoint pairs (where possible)
    if a bp level call is not possible for one of the breakpoints then returns None
    if no breakpoints can be resolved returns the original event only with NO split read evidence
    also sets the SV type call if multiple are input
    """
    pos1 = {}
    pos2 = {}

    for i, breakpoint, d in [(0, ev.break1, pos1), (1, ev.break2, pos2)]:
        for read in ev.split_reads[i]:
            try:
                pos = breakpoint_pos(read, breakpoint.orient) + 1
                print(pos)
                if pos not in d:
                    d[pos] = []
                d[pos].append(read)
            except AttributeError:
                pass
        putative_positions = list(d.keys())
        for pos in putative_positions:
            if len(d[pos]) < ev.min_splits_reads_resolution:
                del d[pos]
            else:
                count = 0
                for r in d[pos]:
                    if not r.has_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT) or \
                            not r.get_tag(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT):
                        count += 1
                if count < ev.min_non_target_aligned_split_reads:
                    del d[pos]

    linked_pairings = []
    # now pair up the breakpoints with their putative partners
    for first, second in itertools.product(pos1, pos2):
        if ev.break1.chr == ev.break2.chr:
            if first >= second:
                continue
        links = 0
        read_names = set([r.query_name for r in pos1[first]])
        for read in pos2[second]:
            if read.query_name in read_names:
                links += 1
        if links < ev.min_linking_split_reads:
            continue
        first_breakpoint = Breakpoint(ev.break1.chr, first, strand=ev.break1.strand, orient=ev.break1.orient)
        second_breakpoint = Breakpoint(ev.break2.chr, second, strand=ev.break2.strand, orient=ev.break2.orient)
        call = EventCall(
            first_breakpoint, second_breakpoint, ev, event_type,
            call_method=CALL_METHOD.SPLIT
        )
        linked_pairings.append(call)

    f = [p for p in pos1 if p not in [t.break1.start for t in linked_pairings]]
    s = [p for p in pos2 if p not in [t.break2.start for t in linked_pairings]]

    for first, second in itertools.product(f, s):
        if ev.break1.chr == ev.break2.chr:
            if first >= second:
                continue
        first_breakpoint = Breakpoint(ev.break1.chr, first, strand=ev.break1.strand, orient=ev.break1.orient)
        second_breakpoint = Breakpoint(ev.break2.chr, second, strand=ev.break2.strand, orient=ev.break2.orient)
        call = EventCall(
            first_breakpoint, second_breakpoint, ev, event_type,
            call_method=CALL_METHOD.SPLIT
        )
        linked_pairings.append(call)

    if len(linked_pairings) == 0:  # then call by mixed or flanking only
        error_messages = set()
        # if can call the first breakpoint by split
        for pos in pos1:
            bp = sys_copy(ev.break1)
            bp.start = pos
            bp.end = pos
            try:
                f, s = _call_by_flanking_pairs(ev, event_type, first_breakpoint_called=bp)
                call = EventCall(
                    f, s, ev, event_type,
                    call_method=CALL_METHOD.SPLIT,
                    break2_call_method=CALL_METHOD.FLANK
                )
                linked_pairings.append(call)
            except (AssertionError, UserWarning) as err:
                error_messages.add(str(err))

        for pos in pos2:
            bp = sys_copy(ev.break2)
            bp.start = pos
            bp.end = pos
            try:
                f, s = _call_by_flanking_pairs(ev, event_type, second_breakpoint_called=bp)
                call = EventCall(
                    f, s, ev, event_type,
                    call_method=CALL_METHOD.FLANK,
                    break2_call_method=CALL_METHOD.SPLIT
                )
                linked_pairings.append(call)
            except (AssertionError, UserWarning) as err:
                error_messages.add(str(err))

        if len(linked_pairings) == 0:  # call by flanking only
            try:
                f, s = _call_by_flanking_pairs(ev, event_type)
                call = EventCall(
                    f, s, ev, event_type,
                    call_method=CALL_METHOD.FLANK
                )
                linked_pairings.append(call)
            except (AssertionError, UserWarning) as err:
                error_messages.add(str(err))
    if len(linked_pairings) == 0:
        raise UserWarning(';'.join(list(error_messages)))
    return linked_pairings