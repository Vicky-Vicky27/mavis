import argparse
from mavis.util import read_inputs
from mavis.constants import COLUMNS, SVTYPE

__version__ = '0.0.1'


def main():
    parser = argparse.ArgumentParser(
        description='Takes mavis summary files and generates custom circos input files',
        add_help=False)
    required = parser.add_argument_group('Required arguments')
    required.add_argument('-n', '--input', help='path to the input file(s)', required=True, nargs='+')
    required.add_argument('-o', '--output', help='path to the output file', required=True)

    optional = parser.add_argument_group('Optional arguments')
    optional.add_argument('-h', '--help', action='help', help='Show this help message and exit')
    optional.add_argument(
        '-v', '--version', action='version', version='%(prog)s version ' + __version__,
        help='outputs the version number')
    args = parser.parse_args()

    bpps = read_inputs(
        args.input,
        require=[COLUMNS.library, 'event_types', COLUMNS.gene1_aliases, COLUMNS.gene2_aliases],
        add={COLUMNS.stranded: False},
        cast={'event_types': lambda x: x.split(';')},
        explicit_strand=True,
        expand_ns=False
    )

    # output
    print('writing:', args.output)
    with open(args.output, 'w') as fh:
        fh.write(
            'libraries\tevent_type\tgene_1\tchromosome_1\tbreakpoint_1'
            '\tgene_2\tchromosome_2\tbreakpoint_2\tread_pairs\tspanning_reads\n')
        for bpp in bpps:
            for et in bpp.data['event_types']:
                SVTYPE.enforce(et)
                if et == SVTYPE.ITRANS:
                    et = SVTYPE.TRANS
                fh.write('\t'.join([str(c) for c in [
                    bpp.library,
                    SVTYPE.enforce(et),
                    bpp.gene1_aliases if bpp.gene1_aliases else 'NA',
                    bpp.break1.chr,
                    int(bpp.break1.center),
                    bpp.gene2_aliases if bpp.gene2_aliases else 'NA',
                    bpp.break2.chr,
                    int(bpp.break2.center),
                    'NA', 'NA'
                ]]) + '\n')

if __name__ == '__main__':
    main()
