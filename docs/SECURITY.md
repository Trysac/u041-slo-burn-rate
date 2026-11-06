# Security notes

## Threat model

`trysac-slo-burn-rate` has no network access and no runtime dependencies. Its only I/O is reading the data and policy files passed to the CLI or to `load_samples` and `load_policy`.

Defended:

- **Oversized input**: data files are read up to 50 MB and policy files up to 1 MB; larger files raise `input_invalid`.
- **Sample volume**: more than 1,000,000 samples raise `too_many_samples`; policies with more than 1000 rules raise `invalid_config`.
- **Malformed data**: non-UTF-8 input, invalid JSON, naive or impossible timestamps, negative, non-integer, boolean or oversized counts (above 999,999,999,999,999), and wrong CSV headers or column counts are rejected with explicit error codes.
- **Deep JSON**: a `RecursionError` during JSON parsing is reported as `input_invalid`.
- **Policy fields**: rule names are restricted to `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}` in policy files; durations must match `<n>m|h|d` with at most six digits; thresholds must be finite and greater than zero.
- **Error messages**: `SLOError` messages are capped at 200 characters and contain no input values beyond the row number.
- **Code execution**: the code never uses `eval`, `exec` or pickle.

Not defended:

- The library does not authenticate or authorize the caller; anyone who can run the CLI can read any file the process can read.
- Symbolic links and file system races are not checked beyond the size limit at read time.
- Timestamps are not checked against any clock; a caller that passes a wrong `now` gets wrong results without an error.
- Memory use is bounded by the sample limit, not by a time or CPU budget.
- Supply chain of the build and CI is handled by repository configuration, not by this package's code.

## Publishing

Releases are published to PyPI with trusted publishing (OIDC) when available, never with a long-lived token stored in the repository.

To report a vulnerability, see [SECURITY.md](../SECURITY.md).
