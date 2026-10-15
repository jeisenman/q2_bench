// Command q2-mcp serves Go-native Q2 MCP APIs.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/jeisenman/q2_bench/adapters/local"
	"github.com/jeisenman/q2_bench/mcpapi"
)

func main() {
	name := flag.String("server", "prod-support", "MCP API to serve")
	transport := flag.String("transport", "stdio", "stdio or streamable-http")
	host := flag.String("host", "127.0.0.1", "HTTP listen host")
	port := flag.Int("port", 8000, "HTTP listen port")
	configPath := flag.String("config", "configurations.yaml", "configuration YAML")
	flag.Parse()

	if err := local.LoadDotEnv(".env"); err != nil {
		log.Fatal(err)
	}
	server, err := mcpapi.NewServer(mcpapi.Config{
		Name: *name, ConfigurationPath: *configPath,
		UpdatesPath:   os.Getenv("PROD_SUPPORT_UPDATES_PATH"),
		OmissionsPath: os.Getenv("PROD_SUPPORT_OMISSIONS_PATH"),
	})
	if err != nil {
		log.Fatal(err)
	}
	if *transport == "stdio" {
		if err := mcpapi.RunStdio(context.Background(), server); err != nil {
			log.Fatal(err)
		}
		return
	}
	if *transport != "streamable-http" {
		log.Fatalf("unsupported transport %q", *transport)
	}
	address := fmt.Sprintf("%s:%d", *host, *port)
	log.Printf("serving %s MCP API at %s/mcp", *name, address)
	mux := http.NewServeMux()
	mux.Handle("/mcp", mcpapi.HTTPHandler(server))
	if err := http.ListenAndServe(address, mux); err != nil {
		log.Fatal(err)
	}
}
