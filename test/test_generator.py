from src import generate_multistory_multibay_frame, solve_linear_static_opensees, validate_model


def test_generate_multistory_multibay_frame_counts_and_solves():
    sheets = generate_multistory_multibay_frame(n_bays=2, n_stories=3, q_beams=-12.0)

    assert len(sheets["nodes"]) == 12
    assert len(sheets["elements"]) == 15
    assert len(sheets["restraints"]) == 3
    assert len(sheets["dist_loads"]) == 6
    assert validate_model(sheets) == []

    results = solve_linear_static_opensees(sheets, 1)

    assert not results["results_nodal"].empty
    assert not results["results_elements"].empty
