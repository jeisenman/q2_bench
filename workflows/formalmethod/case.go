package formalmethod

import "fmt"

func (v *evaluator) caseExpression(e *Expression, env environment, row Row, group []Row) (any, error) {
	if e.Op == "coalesce" {
		for _, a := range e.Args {
			x, err := v.eval(a, env, row, group)
			if err != nil {
				return nil, err
			}
			if x != nil {
				return x, nil
			}
		}
		return nil, nil
	}
	if e.Op == "otherwise" {
		value, found, err := v.caseBranch(e.Args[0], env, row, group)
		if err != nil || found {
			return value, err
		}
		return v.eval(e.Args[1], env, row, group)
	}
	value, _, err := v.caseBranch(e, env, row, group)
	return value, err
}

func (v *evaluator) caseBranch(e *Expression, env environment, row Row, group []Row) (any, bool, error) {
	if e.Op == "ref" {
		if deferred, ok := env[e.Name].(deferredColumn); ok {
			return v.caseBranch(deferred.expression, deferred.bindings, row, group)
		}
		return nil, false, fmt.Errorf("when receiver is not a deferred CASE expression")
	}
	condition, value := 0, 1
	if e.Op == "when_next" {
		prior, found, err := v.caseBranch(e.Args[0], env, row, group)
		if err != nil || found {
			return prior, found, err
		}
		condition, value = 1, 2
	} else if e.Op != "when" {
		return nil, false, fmt.Errorf("otherwise/when receiver is not an unfinished CASE expression")
	}
	test, err := v.eval(e.Args[condition], env, row, group)
	if err != nil {
		return nil, false, err
	}
	if test != nil {
		if _, ok := test.(bool); !ok {
			return nil, false, fmt.Errorf("when condition is not boolean")
		}
	}
	if test != true {
		return nil, false, nil
	}
	x, err := v.eval(e.Args[value], env, row, group)
	return x, true, err
}
