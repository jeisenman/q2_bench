package resourcediscovery

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"

	agent "github.com/jeisenman/q2_bench/agents/resourcediscovery"
)

const tokenURL = "https://login.microsoftonline.com/%s/oauth2/v2.0/token"

// Config contains Resource Discovery OAuth and API settings.
type Config struct {
	BaseURL      string
	TenantID     string
	ClientID     string
	ClientSecret string
	Scope        string
}

// ConfigFromEnvironment loads all required settings.
func ConfigFromEnvironment() (Config, error) {
	names := []string{
		"RESOURCE_DISCOVERY_BASE_URL",
		"RESOURCE_DISCOVERY_TENANT_ID",
		"RESOURCE_DISCOVERY_CLIENT_ID",
		"RESOURCE_DISCOVERY_CLIENT_SECRET",
		"RESOURCE_DISCOVERY_SCOPE",
	}
	values := make(map[string]string, len(names))
	missing := make([]string, 0)
	for _, name := range names {
		values[name] = strings.TrimSpace(os.Getenv(name))
		if values[name] == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		return Config{}, fmt.Errorf(
			"missing Resource Discovery configuration: %s",
			strings.Join(missing, ", "),
		)
	}
	return Config{
		BaseURL: values[names[0]], TenantID: values[names[1]],
		ClientID: values[names[2]], ClientSecret: values[names[3]], Scope: values[names[4]],
	}, nil
}

// HTTPDoer is the minimal HTTP client boundary.
type HTTPDoer interface {
	Do(*http.Request) (*http.Response, error)
}

// APISource searches genuine non-secret metadata through read-only GETs.
type APISource struct {
	Config Config
	Client HTTPDoer
}

// Lookup returns all records matching one identifier.
func (s APISource) Lookup(
	ctx context.Context,
	identifier agent.Identifier,
) ([]map[string]any, error) {
	token, err := s.accessToken(ctx)
	if err != nil {
		return nil, err
	}
	return s.lookupWithToken(ctx, identifier, token)
}

// LookupBatch resolves identifiers with one access-token request.
func (s APISource) LookupBatch(
	ctx context.Context,
	identifiers []agent.Identifier,
) ([][]map[string]any, error) {
	token, err := s.accessToken(ctx)
	if err != nil {
		return nil, err
	}
	results := make([][]map[string]any, len(identifiers))
	for index, identifier := range identifiers {
		results[index], err = s.lookupWithToken(ctx, identifier, token)
		if err != nil {
			return nil, err
		}
	}
	return results, nil
}

func (s APISource) accessToken(ctx context.Context) (string, error) {
	values := url.Values{
		"client_id": {s.Config.ClientID}, "client_secret": {s.Config.ClientSecret},
		"grant_type": {"client_credentials"}, "scope": {s.Config.Scope},
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		fmt.Sprintf(tokenURL, url.PathEscape(s.Config.TenantID)),
		bytes.NewBufferString(values.Encode()),
	)
	if err != nil {
		return "", err
	}
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	var response map[string]any
	if err := s.doJSON(request, &response); err != nil {
		return "", err
	}
	token, ok := response["access_token"].(string)
	if !ok || token == "" {
		return "", fmt.Errorf("Resource Discovery token response is missing access_token")
	}
	return token, nil
}

func (s APISource) lookupWithToken(
	ctx context.Context,
	identifier agent.Identifier,
	token string,
) ([]map[string]any, error) {
	path, queryName, err := query(identifier.Kind)
	if err != nil {
		return nil, err
	}
	endpoint, err := url.Parse(strings.TrimRight(s.Config.BaseURL, "/") + path)
	if err != nil {
		return nil, err
	}
	parameters := endpoint.Query()
	parameters.Set(queryName, identifier.Value)
	endpoint.RawQuery = parameters.Encode()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Accept", "application/json")
	var payload any
	if err := s.doJSON(request, &payload); err != nil {
		return nil, err
	}
	records, err := records(payload)
	if err != nil {
		return nil, err
	}
	for index, record := range records {
		records[index] = normalizeRecord(record)
	}
	return records, nil
}

func (s APISource) doJSON(request *http.Request, output any) error {
	client := s.Client
	if client == nil {
		client = &http.Client{}
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("Resource Discovery request failed with HTTP %d", response.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(body, output); err != nil {
		return fmt.Errorf("Resource Discovery response must be valid JSON: %w", err)
	}
	return nil
}

func query(kind agent.IdentifierKind) (string, string, error) {
	clients := map[agent.IdentifierKind]string{
		agent.ClientID:   "provisionedClientId",
		agent.ClientName: "name",
		agent.Subdomain:  "subdomain",
	}
	if name, exists := clients[kind]; exists {
		return "/api/v1/clients", name, nil
	}
	resources := map[agent.IdentifierKind]string{
		agent.ResourceID: "id", agent.ResourceSet: "resourceSet",
		agent.Environment: "environment", agent.Database: "database",
		agent.Storage: "storage", agent.DataLake: "datalake",
	}
	name, exists := resources[kind]
	if !exists {
		return "", "", fmt.Errorf("unsupported Resource Discovery identifier kind %q", kind)
	}
	return "/api/v1/resources", name, nil
}

func records(payload any) ([]map[string]any, error) {
	switch typed := payload.(type) {
	case map[string]any:
		return []map[string]any{typed}, nil
	case []any:
		records := make([]map[string]any, len(typed))
		for index, item := range typed {
			record, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf(
					"Resource Discovery search response must be an object or list of objects",
				)
			}
			records[index] = record
		}
		return records, nil
	default:
		return nil, fmt.Errorf(
			"Resource Discovery search response must be an object or list of objects",
		)
	}
}

func normalizeRecord(record map[string]any) map[string]any {
	aliases := map[string]string{
		"id": "resource_id", "resourceId": "resource_id",
		"resourceName": "resource_name", "resourceType": "resource_type",
		"provisionedClientId": "provisioned_client_id", "clientId": "client_id",
		"name": "client_name", "clientName": "client_name",
		"resourceSet": "resource_set", "storageAccount": "storage",
		"dataLake": "datalake", "dataLakeAccount": "datalake",
		"reviewedProductionResendUrl": "reviewed_production_resend_url",
		"routingSource":               "routing_source", "prodSupportIgnore": "prod_support_ignore",
	}
	allowed := make(map[string]struct{})
	for _, field := range []string{
		"resource_id", "resource_name", "resource_type", "provisioned_client_id",
		"client_id", "client_name", "subdomain", "environment", "zone", "service",
		"resource_set", "database", "storage", "datalake",
		"reviewed_production_resend_url", "routing_source", "prod_support_ignore",
	} {
		allowed[field] = struct{}{}
	}
	normalized := make(map[string]any)
	for name, value := range record {
		if alias, exists := aliases[name]; exists {
			name = alias
		}
		if _, exists := allowed[name]; exists {
			normalized[name] = value
		}
	}
	if name, ok := normalized["client_name"].(string); ok {
		normalized["client_name"] = agent.ParseClientName(name)
	}
	return normalized
}
