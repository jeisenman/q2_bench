// Command report reconciles frozen inputs and emitted machine draft artifacts.
package main

import (
	"flag"
	"fmt"
	"os"
)

func main() {
	run := flag.String("run", "", "Frozen rollout directory")
	output := flag.String("output", "", "New review directory; must not exist")
	incomplete := flag.Bool("allow-incomplete", false, "Permit a read-only snapshot of pending and unresolved attempts")
	flag.Parse()
	if err := report(*run, *output, *incomplete, 553); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Wrote offline artifact report. No definitions, results, source graph or approvals changed.")
}
