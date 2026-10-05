# Local candidate patch

Upstream: python-hwpx 6.3.0, https://github.com/airmang/python-hwpx, Apache-2.0.
This is an experimental local source copy; it is not an upstream release.
Modified file: hwpx/opc/xml_utils.py. Replace global byte substitutions with
safe structural namespace/QName normalization that preserves XML attribute
values, text, comments and processing instructions. Public document APIs are
unchanged. Original licenses and notice are in licenses/.

No installed package or security settings are changed. Candidate selection is
explicit via scripts/candidate_runtime.py before importing hwpx. All other
source files are checked against the installed dependency inventory in the
HWP011 run evidence. The complete same-input/guard/native/output/re-edit
results belong to that run and do not certify other platforms or versions.
