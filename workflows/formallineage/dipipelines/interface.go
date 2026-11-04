package dipipelines

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/jeisenman/q2_bench/workflows/lineagecheck"
	sitter "github.com/tree-sitter/go-tree-sitter"
)

// DatasetPort records source-declared dataset identity and schema evidence.
// Unset minor versions remain unresolved; latest constants are not run evidence.
type DatasetPort struct {
	SchemaSource  *Source              `json:"schema_source,omitempty"`
	SchemaStatus  string               `json:"schema_status"`
	MetadataClass string               `json:"metadata_class"`
	Source        Source               `json:"source"`
	Name          string               `json:"name"`
	Stage         string               `json:"stage"`
	Provider      string               `json:"provider"`
	Group         string               `json:"group"`
	Dataset       string               `json:"dataset"`
	Major         int                  `json:"major"`
	Minor         *int                 `json:"minor"`
	ReadPolicy    string               `json:"read_policy"`
	Fields        []lineagecheck.Field `json:"fields"`
}

// JobInterface binds a job's declared input/output metadata to pinned sources.
type JobInterface struct {
	Evidence        []Source      `json:"evidence"`
	EntryPoint      string        `json:"entrypoint"`
	Source          Source        `json:"source"`
	Inputs          []DatasetPort `json:"inputs"`
	Outputs         []DatasetPort `json:"outputs"`
	Unresolved      []Diagnostic  `json:"unresolved"`
	PredictionReady bool          `json:"prediction_ready"`
}

type parsedModule struct {
	source    Source
	content   []byte
	tree      *sitter.Tree
	imports   map[string]string
	constants map[string][]*sitter.Node
}
type interfaceResolver struct {
	ctx          context.Context
	root, commit string
	modules      map[string]*parsedModule
	failures     map[string]error
}

func modulePath(module string) (string, error) {
	prefix := ""
	switch strings.Split(module, ".")[0] {
	case "datascience":
		prefix = "de-jobs/src/"
	case "datascience_jobs":
		prefix = "ds-jobs/src/"
	case "datamart":
		prefix = "de-jobs/src/"
	case "rajobs":
		prefix = "ra-jobs/src/"
	default:
		return "", fmt.Errorf("external module %s requires its own repository pin", module)
	}
	path := prefix + strings.ReplaceAll(module, ".", "/") + ".py"
	if !safePath(path) {
		return "", fmt.Errorf("invalid module path")
	}
	return path, nil
}

func (r *interfaceResolver) load(module string) (*parsedModule, error) {
	if err := r.failures[module]; err != nil {
		return nil, err
	}
	if m := r.modules[module]; m != nil {
		return m, nil
	}
	if len(r.modules) >= 500 {
		return nil, fmt.Errorf("metadata closure exceeds 500 modules")
	}
	path, err := modulePath(module)
	if err != nil {
		return nil, err
	}
	b, err := readGit(r.ctx, r.root, r.commit, path)
	if err != nil {
		if r.failures == nil {
			r.failures = map[string]error{}
		}
		r.failures[module] = err
		return nil, err
	}
	tree, err := parse(b)
	if err != nil {
		return nil, err
	}
	m := &parsedModule{Source{Commit: r.commit, Path: path, SHA256: hash(b)}, b, tree, sourceImports(tree.RootNode(), b), moduleConstants(tree.RootNode(), b)}
	r.modules[module] = m
	return m, nil
}

func classNode(m *parsedModule, name string) *sitter.Node {
	for _, n := range children(m.tree.RootNode()) {
		if n.Kind() == "class_definition" && n.ChildByFieldName("name").Utf8Text(m.content) == name {
			return n
		}
	}
	return nil
}

func propertyValue(class *sitter.Node, name string, source []byte) *sitter.Node {
	for _, n := range children(class.ChildByFieldName("body")) {
		if n.Kind() == "decorated_definition" {
			n = n.ChildByFieldName("definition")
		}
		if n.Kind() == "function_definition" && n.ChildByFieldName("name").Utf8Text(source) == name {
			body := children(n.ChildByFieldName("body"))
			if len(body) == 1 && body[0].Kind() == "return_statement" && body[0].NamedChildCount() == 1 {
				return body[0].NamedChild(0)
			}
		}
	}
	return nil
}

// DescribeJob resolves literal metadata declarations without importing job code.
func DescribeJob(ctx context.Context, root, commit, entrypoint string) (JobInterface, error) {
	result := JobInterface{EntryPoint: entrypoint, Inputs: []DatasetPort{}, Outputs: []DatasetPort{}, Unresolved: []Diagnostic{}}
	if !commitRE.MatchString(commit) || root == "" {
		return result, fmt.Errorf("provide checkout and full commit")
	}
	split := strings.LastIndex(entrypoint, ".")
	if split < 1 {
		return result, fmt.Errorf("provide a qualified job class")
	}
	resolver := interfaceResolver{ctx: ctx, root: root, commit: commit, modules: map[string]*parsedModule{}}
	defer func() {
		for _, m := range resolver.modules {
			m.tree.Close()
		}
	}()
	module, err := resolver.load(entrypoint[:split])
	if err != nil {
		return result, err
	}
	result.Source = module.source
	class := classNode(module, entrypoint[split+1:])
	if class == nil {
		return result, fmt.Errorf("job class not found at pin")
	}
	inputs := propertyValue(class, "source_meta_data", module.content)
	outputs := propertyValue(class, "output_meta_data", module.content)
	if inputs == nil {
		inputs = downloaderMetadata(class, module)
	}
	if outputs == nil {
		outputs = classConstant(class, "META", module.content)
	}
	for _, role := range []struct {
		name  string
		node  *sitter.Node
		ports *[]DatasetPort
	}{{"inputs", inputs, &result.Inputs}, {"outputs", outputs, &result.Outputs}} {
		if role.node == nil {
			result.Unresolved = append(result.Unresolved, Diagnostic{Line: int(class.StartPosition().Row) + 1, Message: "no closed metadata declaration for " + role.name})
			continue
		}
		ports, issues := resolver.ports(module, role.node, 0)
		*role.ports = ports
		result.Unresolved = append(result.Unresolved, issues...)
	}
	result.Unresolved = append(result.Unresolved, Diagnostic{Line: int(class.StartPosition().Row) + 1, Message: "runtime input versions, invocation context and linked implementation remain unbound"})
	for _, m := range resolver.modules {
		result.Evidence = append(result.Evidence, m.source)
	}
	sort.Slice(result.Evidence, func(i, j int) bool { return result.Evidence[i].Path < result.Evidence[j].Path })
	return result, nil
}

func sourceImports(root *sitter.Node, b []byte) map[string]string {
	result := map[string]string{}
	for _, n := range children(root) {
		if n.Kind() != "import_from_statement" {
			continue
		}
		module := n.ChildByFieldName("module_name")
		if module == nil {
			continue
		}
		for _, x := range children(n) {
			if x.Id() == module.Id() {
				continue
			}
			name, alias := x.Utf8Text(b), x.Utf8Text(b)
			if x.Kind() == "aliased_import" {
				name = x.ChildByFieldName("name").Utf8Text(b)
				alias = x.ChildByFieldName("alias").Utf8Text(b)
			}
			result[alias] = module.Utf8Text(b) + "." + name
		}
	}
	return result
}

func classConstant(class *sitter.Node, name string, b []byte) *sitter.Node {
	for _, n := range children(class.ChildByFieldName("body")) {
		if n.Kind() == "expression_statement" && n.NamedChildCount() == 1 && n.NamedChild(0).Kind() == "assignment" {
			a := n.NamedChild(0)
			left := a.ChildByFieldName("left")
			if left != nil && left.Utf8Text(b) == name {
				return a.ChildByFieldName("right")
			}
		}
	}
	return nil
}

func downloaderMetadata(class *sitter.Node, m *parsedModule) *sitter.Node {
	var found []*sitter.Node
	var walk func(*sitter.Node)
	walk = func(n *sitter.Node) {
		if n.Kind() == "call" {
			target := n.ChildByFieldName("function")
			if target.Kind() == "attribute" && target.ChildByFieldName("attribute").Utf8Text(m.content) == "from_runner" {
				object := target.ChildByFieldName("object")
				qualified := m.imports[object.Utf8Text(m.content)]
				if strings.HasSuffix(qualified, ".SparkDatasetDownloader") || strings.HasSuffix(qualified, ".PandasDatasetDownloader") {
					args := children(n.ChildByFieldName("arguments"))
					if len(args) > 0 {
						found = append(found, args[0])
					}
				}
			}
		}
		for _, x := range children(n) {
			walk(x)
		}
	}
	walk(class)
	if len(found) == 1 {
		return found[0]
	}
	return nil
}

func (r *interfaceResolver) ports(m *parsedModule, n *sitter.Node, depth int) ([]DatasetPort, []Diagnostic) {
	issue := func(message string) ([]DatasetPort, []Diagnostic) {
		return nil, []Diagnostic{{Line: int(n.StartPosition().Row) + 1, Message: message}}
	}
	if depth > 32 {
		return issue("metadata reference depth exceeds 32")
	}
	if n.Kind() == "identifier" {
		name := n.Utf8Text(m.content)
		if len(m.constants[name]) != 1 {
			return issue("unresolved metadata binding " + name)
		}
		return r.ports(m, m.constants[name][0], depth+1)
	}
	if n.Kind() == "list" || n.Kind() == "tuple" {
		ports := []DatasetPort{}
		issues := []Diagnostic{}
		for _, x := range children(n) {
			p, e := r.ports(m, x, depth+1)
			ports = append(ports, p...)
			issues = append(issues, e...)
		}
		return ports, issues
	}
	if n.Kind() != "call" {
		return issue("computed metadata expression " + n.Kind())
	}
	target := n.ChildByFieldName("function")
	if target.Kind() != "identifier" {
		return issue("dynamic metadata constructor")
	}
	qualified := m.imports[target.Utf8Text(m.content)]
	split := strings.LastIndex(qualified, ".")
	if split < 1 {
		return issue("unresolved metadata class " + target.Utf8Text(m.content))
	}
	owner, err := r.load(qualified[:split])
	if err != nil {
		return issue(err.Error())
	}
	class := classNode(owner, qualified[split+1:])
	if class == nil {
		return issue("metadata class re-export or inheritance requires resolution: " + qualified)
	}
	p := DatasetPort{MetadataClass: qualified, Source: owner.source, Fields: []lineagecheck.Field{}}
	text := func(name string) string {
		declaring, v, err := r.classValue(owner, class, name, 0)
		if err != nil {
			return ""
		}
		s, _ := pythonString(v.Utf8Text(declaring.content))
		return s
	}
	p.Stage = text("PATH_STAGE")
	p.Provider = text("PATH_PROVIDER")
	p.Group = text("PATH_GROUP")
	p.Dataset = text("DATASET_NAME")
	p.Name = sourceNameDefault(class, owner.content)
	issues := []Diagnostic{}
	for _, arg := range children(n.ChildByFieldName("arguments")) {
		if arg.Kind() != "keyword_argument" {
			issues = append(issues, Diagnostic{Line: int(n.StartPosition().Row) + 1, Message: "positional metadata arguments require binding"})
			continue
		}
		key := arg.ChildByFieldName("name").Utf8Text(m.content)
		value := arg.ChildByFieldName("value")
		switch key {
		case "major_version", "minor_version":
			number, err := metadataNumber(m, value, owner, class, qualified)
			if err != nil {
				issues = append(issues, Diagnostic{Line: int(value.StartPosition().Row) + 1, Message: err.Error()})
				continue
			}
			if key == "major_version" {
				p.Major = number
			} else {
				p.Minor = &number
			}
		case "dates_to_download":
			p.ReadPolicy = value.Utf8Text(m.content)
		case "data_source_name":
			name, err := pythonString(value.Utf8Text(m.content))
			if err != nil {
				issues = append(issues, Diagnostic{Line: int(value.StartPosition().Row) + 1, Message: "computed data source name"})
			} else {
				p.Name = name
			}
		}
	}
	if p.Name == "" || p.Stage == "" || p.Provider == "" || p.Group == "" || p.Dataset == "" || p.Major < 1 {
		issues = append(issues, Diagnostic{Line: int(n.StartPosition().Row) + 1, Message: "incomplete dataset identity or major version"})
	}
	if p.Major > 0 {
		p.SchemaStatus = "unknown"
		declaring, schemaClass, inheritErr := r.schemaOwner(owner, class, p.Major, 0)
		var fields []lineagecheck.Field
		var err error
		if inheritErr != nil {
			err = inheritErr
		} else {
			fields, err = lineagecheck.ExtractSchema(declaring.content, schemaClass.ChildByFieldName("name").Utf8Text(declaring.content), p.Major)
		}
		if err != nil {
			issues = append(issues, Diagnostic{Line: int(class.StartPosition().Row) + 1, Message: "schema unresolved: " + err.Error()})
		} else {
			p.Fields = fields
			p.SchemaStatus = "extracted"
			receipt := declaring.source
			p.SchemaSource = &receipt
		}
	}
	sort.Slice(p.Fields, func(i, j int) bool { return p.Fields[i].Name < p.Fields[j].Name })
	return []DatasetPort{p}, issues
}
