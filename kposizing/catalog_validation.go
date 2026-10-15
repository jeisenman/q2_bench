package kposizing

import (
	"fmt"
	"path/filepath"
	"strings"
)

func init() {
	if err := validateCatalog(staticJobTemplates()); err != nil {
		panic("invalid KPO job-template catalog: " + err.Error())
	}
}

func validateCatalog(templates []JobTemplate) error {
	seenNames := make(map[string]string)
	for index, template := range templates {
		if err := validateJobTemplate(template); err != nil {
			return fmt.Errorf("template %d: %w", index, err)
		}
		for _, name := range append([]string{template.Job}, template.Aliases...) {
			if strings.TrimSpace(name) == "" || name != strings.TrimSpace(name) {
				return fmt.Errorf("%s: canonical names and aliases must be non-blank and trimmed", template.Job)
			}
			if owner, exists := seenNames[name]; exists {
				return fmt.Errorf("name %q is shared by %q and %q", name, owner, template.Job)
			}
			seenNames[name] = template.Job
		}
	}
	return nil
}

func validateJobTemplate(template JobTemplate) error {
	if strings.TrimSpace(template.Job) == "" || template.Job != strings.TrimSpace(template.Job) {
		return fmt.Errorf("canonical job must be non-blank and trimmed")
	}
	if err := template.DefaultRunner.Validate(); err != nil {
		return fmt.Errorf("%s: %w", template.Job, err)
	}
	if err := template.DefaultFamily.Validate(); err != nil {
		return fmt.Errorf("%s: %w", template.Job, err)
	}
	if err := template.InputMode.Validate(); err != nil {
		return fmt.Errorf("%s: %w", template.Job, err)
	}
	if err := template.AuxiliaryInput.Validate(); err != nil {
		return fmt.Errorf("%s: %w", template.Job, err)
	}
	if template.CopyConcurrency < 0 || template.UploadConcurrency < 0 {
		return fmt.Errorf("%s: known concurrency cannot be negative", template.Job)
	}
	if len(template.RunnerChoices) == 0 {
		return fmt.Errorf("%s: runner choices must not be empty", template.Job)
	}
	defaultFound := false
	seenRoutes := make(map[string]struct{})
	for _, route := range template.RunnerChoices {
		if err := route.Runner.Validate(); err != nil {
			return fmt.Errorf("%s route: %w", template.Job, err)
		}
		if err := route.Family.Validate(); err != nil {
			return fmt.Errorf("%s route: %w", template.Job, err)
		}
		if err := route.AuxiliaryInput.Validate(); err != nil {
			return fmt.Errorf("%s route: %w", template.Job, err)
		}
		key := string(route.Runner) + "/" + string(route.Family)
		if _, exists := seenRoutes[key]; exists {
			return fmt.Errorf("%s: duplicate runner route %s", template.Job, key)
		}
		seenRoutes[key] = struct{}{}
		isDefault := route.Runner == template.DefaultRunner && route.Family == template.DefaultFamily
		defaultFound = defaultFound || isDefault
		if isDefault && route.AuxiliaryInput != template.AuxiliaryInput {
			return fmt.Errorf(
				"%s: default runner route auxiliary input %q contradicts template default %q",
				template.Job,
				route.AuxiliaryInput,
				template.AuxiliaryInput,
			)
		}
		if !isDefault && strings.TrimSpace(route.Condition) == "" {
			return fmt.Errorf("%s: alternative runner route %s requires a condition", template.Job, key)
		}
		if len(route.Provenance) == 0 {
			return fmt.Errorf("%s: runner route %s requires provenance", template.Job, key)
		}
		if err := validateProvenance(template.Job, route.Provenance); err != nil {
			return err
		}
	}
	if !defaultFound {
		return fmt.Errorf("%s: default runner and family are not an allowed route", template.Job)
	}
	if err := validateSource(template); err != nil {
		return err
	}
	if len(template.Provenance) == 0 {
		return fmt.Errorf("%s: provenance must not be empty", template.Job)
	}
	return validateProvenance(template.Job, template.Provenance)
}

func validateProvenance(job string, references []ProvenanceRef) error {
	for _, provenance := range references {
		if strings.TrimSpace(provenance.Repository) == "" ||
			strings.TrimSpace(provenance.Symbol) == "" ||
			provenance.File == "" ||
			filepath.IsAbs(provenance.File) ||
			filepath.Clean(provenance.File) != provenance.File ||
			strings.HasPrefix(provenance.File, "..") {
			return fmt.Errorf("%s: provenance must use a stable repo-relative file and symbol", job)
		}
	}
	return nil
}

func validateSource(template JobTemplate) error {
	source := template.Source
	if template.InputMode == InputModeRAFile && strings.TrimSpace(source.File) == "" {
		return fmt.Errorf("%s: RA-file input requires a source file", template.Job)
	}
	if template.InputMode != InputModeRAFile &&
		(strings.TrimSpace(source.Dataset) == "" ||
			strings.TrimSpace(source.Stage) == "" ||
			strings.TrimSpace(source.Version) == "") {
		return fmt.Errorf("%s: historical input requires dataset, stage, and version", template.Job)
	}
	return nil
}
