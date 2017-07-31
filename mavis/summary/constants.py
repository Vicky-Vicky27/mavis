from ..util import MavisNamespace
from vocab import Vocab

DEFAULTS = MavisNamespace(
    filter_min_remapped_reads=5,
    filter_min_spanning_reads=5,
    filter_min_flanking_reads=5,
    filter_min_flanking_only_reads=10,
    filter_min_split_reads=5,
    filter_min_linking_split_reads=1
)

PAIRING_STATE = Vocab(
    EXP='expressed',
    NO_EXP='not expressed',
    SOMATIC='somatic',
    GERMLINE='germline',
    CO_EXP='co-expressed',
    GERMLINE_EXP='germline expression',
    SOMATIC_EXP='somatic expression',
    MATCH='matched',
    NO_MATCH='not matched',
    GENOMIC='genomic support',
    NO_GENOMIC='no genomic support'
)