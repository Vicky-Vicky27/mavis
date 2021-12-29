import os
import re
from pathlib import Path

from setuptools import find_packages, setup

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()
VERSION = '2.2.8'


def check_nonpython_dependencies():
    """
    check that the non-python dependencies have been installed.

    Raises:
        OSError: A dependency is not installed
    """
    import shutil

    aligner = (
        os.environ['MAVIS_ALIGNER']
        if 'MAVIS_ALIGNER' in os.environ and os.environ['MAVIS_ALIGNER']
        else 'blat'
    )
    aligner = re.split(r'\s+', aligner)[0]
    pth = shutil.which(aligner)
    if not pth:
        print('WARNING: Aligner is required. Missing executable: {}'.format(aligner))
    else:
        print('Found: aligner at', pth)


# HSTLIB is a dependency for pysam.
# The cram file libraries fail for some OS versions and mavis does not use cram files so we disable these options
os.environ['HTSLIB_CONFIGURE_OPTIONS'] = '--disable-lzma --disable-bz2 --disable-libcurl'


TEST_REQS = [
    'timeout-decorator>=0.3.3',
    'coverage>=4.2',
    'pycodestyle>=2.3.1',
    'pytest',
    'pytest-cov',
]


DOC_REQS = [
    'mkdocs==1.1.2',
    'markdown_refdocs',
    'mkdocs-material==5.4.0',
    'markdown-include',
    'mkdocs-simple-hooks==0.1.2',
]


INSTALL_REQS = [
    'Distance>=0.1.3',
    'Shapely>=1.6.4.post1',
    'biopython>=1.70, <1.78',
    'braceexpand==0.1.2',
    'colour',
    'networkx>=2.5,<3',
    'numpy>=1.13.1',
    'pandas>=1.1, <2',
    'pysam',
    'shortuuid>=0.5.0',
    'svgwrite',
    'mavis_config>=1.1.0, <2.0.0',
]

DEPLOY_REQS = ['twine', 'wheel']


setup(
    name='mavis',
    version='{}'.format(VERSION),
    url='https://github.com/bcgsc/mavis.git',
    download_url='https://github.com/bcgsc/mavis/archive/v{}.tar.gz'.format(VERSION),
    package_dir={'': 'src'},
    packages=find_packages(where='src'),
    description='A Structural Variant Post-Processing Package',
    long_description=long_description,
    long_description_content_type='text/markdown',
    install_requires=INSTALL_REQS,
    extras_require={
        'docs': DOC_REQS,
        'test': TEST_REQS,
        'dev': ['black==20.8b1', 'flake8'] + DOC_REQS + TEST_REQS + DEPLOY_REQS,
        'deploy': DEPLOY_REQS,
        'tools': ['pyensembl', 'simplejson'],
    },
    tests_require=TEST_REQS,
    setup_requires=['pip>=9.0.0', 'setuptools>=36.0.0'],
    python_requires='>=3.7',
    author='Caralyn Reisle',
    author_email='creisle@bcgsc.ca',
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'mavis = mavis.main:main',
            'calculate_ref_alt_counts = tools.calculate_ref_alt_counts:main',
        ]
    },
    include_package_data=True,
    data_files=[('mavis', ['src/mavis/schemas/config.json', 'src/mavis/schemas/overlay.json'])],
    project_urls={'mavis': 'http://mavis.bcgsc.ca'},
)
check_nonpython_dependencies()
