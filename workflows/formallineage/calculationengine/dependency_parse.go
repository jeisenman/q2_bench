package calculationengine

import (
	"bytes"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"sort"
	"strings"
)

func parseBuild(b []byte, f *DependencyFile) error {
	decoder := xml.NewDecoder(bytes.NewReader(bytes.TrimPrefix(b, []byte{0xef, 0xbb, 0xbf})))
	conditions := []string{}
	for {
		token, err := decoder.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return err
		}
		switch t := token.(type) {
		case xml.StartElement:
			attrs := map[string]string{}
			for _, a := range t.Attr {
				attrs[a.Name.Local] = a.Value
			}
			condition := attrs["Condition"]
			if len(conditions) > 0 && conditions[len(conditions)-1] != "" {
				if condition != "" {
					condition = "(" + conditions[len(conditions)-1] + ") AND (" + condition + ")"
				} else {
					condition = conditions[len(conditions)-1]
				}
			}
			switch t.Name.Local {
			case "Project":
				f.SDK = attrs["Sdk"]
			case "TargetFramework", "TargetFrameworks":
				var value string
				if err := decoder.DecodeElement(&value, &t); err != nil {
					return err
				}
				f.Frameworks = append(f.Frameworks, value)
				continue
			case "PackageReference", "ProjectReference", "PackageVersion", "Import", "Sdk":
				var node struct {
					Version       string `xml:"Version"`
					PrivateAssets string `xml:"PrivateAssets"`
					IncludeAssets string `xml:"IncludeAssets"`
					ExcludeAssets string `xml:"ExcludeAssets"`
				}
				if err := decoder.DecodeElement(&node, &t); err != nil {
					return err
				}
				name := attrs["Include"]
				if name == "" {
					name = attrs["Update"]
				}
				if t.Name.Local == "Import" {
					name = attrs["Project"]
				}
				if t.Name.Local == "Sdk" {
					name = attrs["Name"]
				}
				if name == "" {
					return fmt.Errorf("%s is missing dependency name", t.Name.Local)
				}
				version := attrs["Version"]
				if version == "" {
					version = node.Version
				}
				metadata := attrs
				for k, v := range map[string]string{"PrivateAssets": node.PrivateAssets, "IncludeAssets": node.IncludeAssets, "ExcludeAssets": node.ExcludeAssets} {
					if v != "" {
						metadata[k] = v
					}
				}
				f.Entries = append(f.Entries, Dependency{Kind: t.Name.Local, Name: name, Version: version, Condition: condition, Metadata: metadata})
				continue
			}
			conditions = append(conditions, condition)
		case xml.EndElement:
			if len(conditions) == 0 {
				return fmt.Errorf("invalid MSBuild element stack")
			}
			conditions = conditions[:len(conditions)-1]
		}
	}
	return nil
}

func sortedKeys[V any](values map[string]V) []string {
	keys := make([]string, 0, len(values))
	for k := range values {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func parsePackage(b []byte, f *DependencyFile) error {
	var manifest map[string]json.RawMessage
	if err := json.Unmarshal(b, &manifest); err != nil {
		return err
	}
	for _, kind := range []string{"dependencies", "devDependencies", "peerDependencies", "optionalDependencies"} {
		if raw, ok := manifest[kind]; ok {
			var deps map[string]string
			if err := json.Unmarshal(raw, &deps); err != nil {
				return fmt.Errorf("%s: %w", kind, err)
			}
			for _, name := range sortedKeys(deps) {
				f.Entries = append(f.Entries, Dependency{Kind: kind, Name: name, Version: deps[name]})
			}
		}
	}
	for _, key := range []string{"engines", "packageManager", "scripts", "workspaces"} {
		if raw, ok := manifest[key]; ok {
			f.Entries = append(f.Entries, Dependency{Kind: "npm-configuration", Name: key, Metadata: map[string]string{"declaration": string(raw)}})
		}
	}
	return nil
}

func parseLock(b []byte, f *DependencyFile) error {
	var lock struct {
		Version  int `json:"lockfileVersion"`
		Packages map[string]struct {
			Name                 string            `json:"name"`
			Version              string            `json:"version"`
			Link                 bool              `json:"link"`
			Dev                  bool              `json:"dev"`
			Optional             bool              `json:"optional"`
			Resolved             string            `json:"resolved"`
			Integrity            string            `json:"integrity"`
			Dependencies         map[string]string `json:"dependencies"`
			OptionalDependencies map[string]string `json:"optionalDependencies"`
			PeerDependencies     map[string]string `json:"peerDependencies"`
		} `json:"packages"`
	}
	if err := json.Unmarshal(b, &lock); err != nil {
		return err
	}
	if (lock.Version != 2 && lock.Version != 3) || lock.Packages == nil {
		return fmt.Errorf("requires npm lockfile v2/v3 packages contract")
	}
	f.LockVersion = lock.Version
	for _, location := range sortedKeys(lock.Packages) {
		if location == "" {
			continue
		}
		p := lock.Packages[location]
		name := p.Name
		if name == "" {
			i := strings.LastIndex(location, "node_modules/")
			if i < 0 {
				return fmt.Errorf("lock entry %q has no package name", location)
			}
			name = location[i+len("node_modules/"):]
		}
		if p.Version == "" && !p.Link {
			return fmt.Errorf("lock entry %q has no version", location)
		}
		f.Entries = append(f.Entries, Dependency{Kind: "npm-lock", Name: name, Version: p.Version, Location: location, Metadata: map[string]string{"resolved": p.Resolved, "integrity": p.Integrity, "dev": fmt.Sprint(p.Dev), "optional": fmt.Sprint(p.Optional), "link": fmt.Sprint(p.Link)}, Dependencies: p.Dependencies, OptionalDependencies: p.OptionalDependencies, PeerDependencies: p.PeerDependencies})
	}
	return nil
}
