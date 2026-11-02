package mcpapi

import (
	"context"
	"fmt"
	"os"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/lineagecheck"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type lineageCompareInput struct {
	BaseID string              `json:"base_id"`
	HeadID string              `json:"head_id"`
	Policy lineagecheck.Policy `json:"policy"`
}

type lineageBackfillInput struct {
	SnapshotID string                    `json:"snapshot_id"`
	Plan       lineagecheck.BackfillPlan `json:"plan"`
}

type lineageManifestInput struct {
	SnapshotID string `json:"snapshot_id,omitempty"`
}

func localLineageStore() lineagecheck.Store {
	root := strings.TrimSpace(os.Getenv("LINEAGE_STORE_PATH"))
	if root == "" {
		root = lineagecheck.DefaultStorePath
	}
	return lineagecheck.Store{Root: root}
}

func registerLineageChecks(server *mcp.Server, store lineagecheck.Store) {
	mcp.AddTool(server, &mcp.Tool{Name: "get_lineage_manifest", Description: "Read a verified local structural snapshot, its source pins, and reviewed scope. An empty ID selects latest.", Annotations: lineageReadOnlyAnnotations()}, func(ctx context.Context, _ *mcp.CallToolRequest, in lineageManifestInput) (*mcp.CallToolResult, lineagecheck.Snapshot, error) {
		s, err := store.Load(ctx, in.SnapshotID)
		return nil, s, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "compare_lineage_versions", Description: "Check additive compatibility or declared input replacements between two local snapshots. Unknown evidence blocks a passing report.", Annotations: lineageReadOnlyAnnotations()}, func(ctx context.Context, _ *mcp.CallToolRequest, in lineageCompareInput) (*mcp.CallToolResult, lineagecheck.Report, error) {
		if in.BaseID == "" || in.HeadID == "" {
			return nil, lineagecheck.Report{}, fmt.Errorf("comparison requires explicit base_id and head_id")
		}
		base, err := store.Load(ctx, in.BaseID)
		if err != nil {
			return nil, lineagecheck.Report{}, err
		}
		head, err := store.Load(ctx, in.HeadID)
		if err != nil {
			return nil, lineagecheck.Report{}, err
		}
		r, err := lineagecheck.Compare(base, head, in.Policy)
		return nil, r, err
	})
	mcp.AddTool(server, &mcp.Tool{Name: "compare_lineage_backfill", Description: "Compare affected columns with a source-pinned replay plan, including historical windows, forced replay, copies, and ordering within the reviewed scope.", Annotations: lineageReadOnlyAnnotations()}, func(ctx context.Context, _ *mcp.CallToolRequest, in lineageBackfillInput) (*mcp.CallToolResult, lineagecheck.Report, error) {
		if in.SnapshotID == "" {
			return nil, lineagecheck.Report{}, fmt.Errorf("backfill comparison requires an explicit snapshot_id")
		}
		s, err := store.Load(ctx, in.SnapshotID)
		if err != nil {
			return nil, lineagecheck.Report{}, err
		}
		r, err := lineagecheck.CheckBackfill(s, in.Plan)
		return nil, r, err
	})
}
