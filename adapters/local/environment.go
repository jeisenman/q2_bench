package local

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"unicode"
)

// LoadDotEnv loads variables from a dotenv file without overriding the
// process environment. A missing file is treated as optional configuration.
func LoadDotEnv(path string) error {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return fmt.Errorf("open dotenv file %s: %w", path, err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "export ") {
			line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		}
		name, value, found := strings.Cut(line, "=")
		if !found {
			return fmt.Errorf(
				"parse dotenv file %s line %d: expected NAME=value",
				path,
				lineNumber,
			)
		}
		name = strings.TrimSpace(name)
		if !validEnvironmentName(name) {
			return fmt.Errorf(
				"parse dotenv file %s line %d: invalid variable name %q",
				path,
				lineNumber,
				name,
			)
		}
		value, err = parseDotEnvValue(strings.TrimSpace(value))
		if err != nil {
			return fmt.Errorf(
				"parse dotenv file %s line %d: %w",
				path,
				lineNumber,
				err,
			)
		}
		if _, exists := os.LookupEnv(name); exists {
			continue
		}
		if err := os.Setenv(name, value); err != nil {
			return fmt.Errorf("set dotenv variable %s: %w", name, err)
		}
	}
	if err := scanner.Err(); err != nil {
		return fmt.Errorf("read dotenv file %s: %w", path, err)
	}
	return nil
}

func parseDotEnvValue(value string) (string, error) {
	if value == "" || value[0] != '"' {
		if len(value) >= 2 && value[0] == '\'' && value[len(value)-1] == '\'' {
			return value[1 : len(value)-1], nil
		}
		return value, nil
	}
	parsed, err := strconv.Unquote(value)
	if err != nil {
		return "", fmt.Errorf("invalid quoted value: %w", err)
	}
	return parsed, nil
}

func validEnvironmentName(name string) bool {
	for index, character := range name {
		if index == 0 {
			if character != '_' && !unicode.IsLetter(character) {
				return false
			}
			continue
		}
		if character != '_' && !unicode.IsLetter(character) && !unicode.IsDigit(character) {
			return false
		}
	}
	return name != ""
}
