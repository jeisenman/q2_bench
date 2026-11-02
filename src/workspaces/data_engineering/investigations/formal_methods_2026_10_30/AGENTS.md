# Mechanistic formal-method validation

The production compiler and independent bounded evaluator are Go code in
`workflows/formalmethod`. Tree-sitter's standard Python grammar is the source
parser. This directory contains only Databricks notebook source and evidence
preparation for differential validation. All Python execution is remote.

`compare.py` receives immutable source bytes, typed methods, synthetic bindings,
and row bags already predicted by Go. CPython AST selects original source
functions, without importing application modules. Spark evaluates those
original functions over in-memory synthetic inputs. No downloaders, uploaders,
production datasets, or application storage calls are available to the selected
functions. Verify source SHA256 before evaluating and compare complete row bags.

Copies belong to their transformation's unit and must ultimately appear as
separate target datasets in its effects. Source parsing, executable helper
coverage, linked job coverage, and Databricks agreement are separate claims.
Do not count unknown methods or excluded framework behavior as passes.

Use existing remote-data tools to wrap and submit reviewed exact SOURCE to the
approved DE workspace/cluster. Retrieve child task output through Jobs API and
inspect embedded results. No local Python or local execution of job code.
