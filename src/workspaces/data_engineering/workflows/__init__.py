"""Deterministic tool compositions invoked by harness skills.

A workflow fixes the control flow over typed tools: no model chooses the next
step. The agent loop belongs to the harness, which reaches these compositions
through MCP.
"""
