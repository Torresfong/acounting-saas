def test_deliberate_failure_to_prove_ci_blocks_merging():
    assert False, "Intentional: proves a failing test blocks merging into main (issue #26)"
