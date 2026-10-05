# Desktop environment

Run the package root's `Install-HangulSkills.ps1` when installing on a new Windows PC.
It discovers the current user/CODEX_HOME, an appropriate Python environment, and the
registered Hangul executable. Read this skill's `environment.json` for the actual
paths and readiness state. Installation does not mean native document work is ready.

For Python work, read `pythonPath` from the sibling hwpx skill's `environment.json`.
If it is null, report the missing Python prerequisite; do not silently use another Python.
PDF verification dependencies have a separate status.

`CodexHancomFilePathChecker` was a source-PC registry alias, not a Hancom-required
DLL name. Native workers now read the configured alias. By default no security
module is selected and native document operations stop before opening a document.

Only an existing registered module whose provenance and access policy have been
reviewed may be selected at installation. This requires its registry name, expected
SHA256, policy evidence file, and explicit review confirmation. The installer never
installs a security DLL or writes registry/security settings. Do not use an automatic
allow-all module as a substitute. Review confirmation records a human decision;
it does not prove the module's policy automatically.

Workers recheck the registry path, file hash, policy evidence hash, disabled state,
and DLL/Hangul PE architecture before RegisterModule. Changes invalidate the
selection. A matching hash or successful RegisterModule does not prove document
permissions or final rendering. Retain the existing native output verification.

`check_hancom_com.ps1` reports comCreated, registerModuleCalled, and
securityModuleRegistered separately. Null means not called. No document is opened.
Compare ordinary Windows user execution when sandbox COM activation fails.
Do not change execution policies or bypass file approval dialogs to make a test pass.
