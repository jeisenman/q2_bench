package calculationengine

import "testing"

func TestBuildReferencesConditionsAndVersions(t *testing.T) {
	f := DependencyFile{}
	b := []byte(`<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup><ItemGroup Condition="'$(T)' == 'test'"><PackageReference Include="Example"><Version>1.2.3</Version><PrivateAssets>all</PrivateAssets></PackageReference><ProjectReference Include="../Engine/Engine.csproj" Condition="'$(X)' == 'true'" /></ItemGroup><Sdk Name="Microsoft.Build.Traversal" Version="2.0.24" /></Project>`)
	if err := parseBuild(b, &f); err != nil {
		t.Fatal(err)
	}
	if f.SDK != "Microsoft.NET.Sdk" || len(f.Entries) != 3 || f.Entries[0].Version != "1.2.3" || f.Entries[0].Condition != "'$(T)' == 'test'" || f.Entries[0].Metadata["PrivateAssets"] != "all" || f.Entries[1].Condition != "('$(T)' == 'test') AND ('$(X)' == 'true')" {
		t.Fatalf("lost build metadata %+v", f)
	}
	if err := parseBuild([]byte(`<Project><PackageReference /></Project>`), &DependencyFile{}); err == nil {
		t.Fatal("accepted missing package name")
	}
	if err := parseBuild([]byte(`<Project><broken></Project>`), &DependencyFile{}); err == nil {
		t.Fatal("accepted malformed XML")
	}
}

func TestNpmLockIdentityAndEdges(t *testing.T) {
	f := DependencyFile{}
	b := []byte(`{"lockfileVersion":3,"packages":{"":{},"node_modules/@scope/pkg":{"version":"1.2.3","dependencies":{"child":"^1"},"peerDependencies":{"peer":"2"}},"node_modules/child":{"version":"1.0.0"},"node_modules/@scope/pkg/node_modules/child":{"version":"2.0.0"}}}`)
	if err := parseLock(b, &f); err != nil {
		t.Fatal(err)
	}
	if len(f.Entries) != 3 || f.Entries[0].Name != "@scope/pkg" || f.Entries[0].Dependencies["child"] != "^1" || f.Entries[0].PeerDependencies["peer"] != "2" {
		t.Fatalf("lost npm identity %+v", f)
	}
	for _, bad := range []string{`{"lockfileVersion":1}`, `{"lockfileVersion":3,"packages":{"node_modules/x":{}}}`, `{bad`} {
		if err := parseLock([]byte(bad), &DependencyFile{}); err == nil {
			t.Fatalf("accepted bad lock %s", bad)
		}
	}
	f = DependencyFile{}
	if err := parsePackage([]byte(`{"dependencies":{"a":"1"},"devDependencies":{"b":"2"},"scripts":{"test":"node test"}}`), &f); err != nil || len(f.Entries) != 3 {
		t.Fatalf("manifest %v %+v", err, f)
	}
}
