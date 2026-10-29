# Local candidate patch

Upstream: python-hwpx 6.3.0, https://github.com/airmang/python-hwpx, Apache-2.0.
This is an experimental local source copy; it is not an upstream release.
Modified file: hwpx/opc/xml_utils.py. Replace global byte substitutions with
safe structural namespace/QName normalization that preserves XML attribute
values, text, comments and processing instructions. Public document APIs are
unchanged. Original licenses and notice are in licenses/.

Modified file: hwpx/oxml/paragraph.py. Paragraph removal resolves the direct
owner inside the wrapper's section tree. Cell and nested-cell paragraphs are
removed from their own sublist. Removing an owner's last paragraph or using
a detached wrapper raises ValueError instead of reporting a successful no-op.
The public method signature is unchanged.

No installed package or security settings are changed. Candidate selection is
explicit via scripts/candidate_runtime.py before importing hwpx. All other
source files were checked against the installed dependency inventory in the
HWP011 run evidence. The complete same-input/guard/native/output/re-edit
results belong to that run and do not certify other platforms or versions.
The paragraph-removal change has separate public batch reproduction and
ownership regression tests in tests/test_table_ownership_alignment.py.
Its structural checks do not claim native rendering verification.
