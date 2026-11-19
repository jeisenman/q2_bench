// Command prepare freezes deterministic inputs for a single-pass dataset rollout.
package main

import (
	"flag"
	"fmt"
	"os"
)

const expectedGeneration = "e020475b-bc7b-40d7-9652-00935e2565fd"
const expectedPrompt = "6c876bc7a89ae483a6cfead9384fb37de14a60069c8e0852e20171616ae62226"
const expectedRequests = "3fab405cfee4b55e458bb98810625fddb2228a9496e7ba503ed8c31b77d777f8"
const expectedCorpus = "2026-09-02T205953Z-zendesk-corpus"
const expectedPolicy = "159dba53422426d10890b21e884340a63d60c5b5a0c82a3e42ef23be95cebb7c"
const expectedGraph = "f5211952368deddeacc47ab989ef6ed8305fd67831ae495a7c4f98bd32ff06f0"

type config struct {
	graph, staged, requests, responses, corpus, prompt, output, cleanupPolicy, generationManifest, modelCapacity string
	measureComponents                                                                                            bool
}

func main() {
	var c config
	flag.StringVar(&c.graph, "graph", "", "Frozen local HTTP graph JSON")
	flag.StringVar(&c.staged, "staged", "var/lineage/di-pipelines.json", "Validated staged semantic graph")
	flag.StringVar(&c.requests, "requests", "", "Exact published requests-zendesk-v2.1-final.jsonl")
	flag.StringVar(&c.responses, "responses", "", "Corresponding published responses.jsonl")
	flag.StringVar(&c.corpus, "corpus", "", "Approved frozen corpus directory; required")
	flag.StringVar(&c.prompt, "prompt", "src/workspaces/data_engineering/investigations/zendesk_dataset_rollout_20261119/prompts/2.0.0.md", "Pinned prompt")
	flag.StringVar(&c.output, "output", "", "New run directory; must not exist")
	flag.StringVar(&c.cleanupPolicy, "cleanup-policy", "conservative", "conservative or single-luna-pass")
	flag.StringVar(&c.generationManifest, "generation-manifest", "", "Explicit generation manifest; defaults to manifest.json beside responses")
	flag.BoolVar(&c.measureComponents, "measure-components", false, "Read-only component measurement; writes no run or report files")
	flag.StringVar(&c.modelCapacity, "model-capacity", "", "Pinned capacity metadata for gpt-6-luna")
	flag.Parse()
	if err := prepare(c); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if !c.measureComponents {
		fmt.Println("Prepared exactly 553 frozen dataset inputs. No model calls or publication.")
	}
}
