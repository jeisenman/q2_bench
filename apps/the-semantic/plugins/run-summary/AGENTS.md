# Run summary page

Trusted static page assets are served by the local research API. This sandboxed
page accepts one host-created MessageChannel and validates a result containing
only title, model, status, and output. Internal identifiers, digests, traces,
errors, and numeric measurements stay in service records. The page renders text
with DOM APIs. No API reads, network calls, HTML injection, execution commands
or Node access. Host and page must reject unknown wire shapes.
