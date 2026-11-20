# Run summary page

Trusted static page assets are served by the local research API. This sandboxed
page accepts one host-created MessageChannel and validates versioned selected
ResearchRecord evidence. It renders text and SVG with DOM APIs. No API reads,
network calls, HTML injection, execution commands or Node access. Missing metrics
are reported explicitly. Host and page must reject unknown wire shapes.
