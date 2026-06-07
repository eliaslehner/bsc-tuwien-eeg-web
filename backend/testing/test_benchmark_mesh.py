import unittest

from benchmark_mesh import (
    format_latex_number,
    parse_float_list,
    summarize_by_algorithm,
)


class BenchmarkMeshHelpersTest(unittest.TestCase):
    def test_parse_float_list_accepts_comma_separated_values(self):
        self.assertEqual(parse_float_list("0.10,0.15, 0.20"), [0.10, 0.15, 0.20])

    def test_parse_float_list_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            parse_float_list(" , ")

    def test_summarize_by_algorithm_computes_mean_and_sample_std(self):
        rows = [
            {"algorithm": "alpha_shapes", "mesh_time_s": 1.0, "raw_faces": 10},
            {"algorithm": "alpha_shapes", "mesh_time_s": 3.0, "raw_faces": 14},
            {"algorithm": "marching_cubes", "mesh_time_s": 4.0, "raw_faces": 100},
        ]

        summary = summarize_by_algorithm(rows, ["mesh_time_s", "raw_faces"])

        self.assertEqual(summary["alpha_shapes"]["runs"], 2)
        self.assertEqual(summary["alpha_shapes"]["mesh_time_s_mean"], 2.0)
        self.assertAlmostEqual(summary["alpha_shapes"]["mesh_time_s_std"], 1.41421356)
        self.assertEqual(summary["alpha_shapes"]["raw_faces_mean"], 12.0)
        self.assertEqual(summary["marching_cubes"]["mesh_time_s_std"], 0.0)

    def test_format_latex_number_handles_missing_values_and_precision(self):
        self.assertEqual(format_latex_number(None), "--")
        self.assertEqual(format_latex_number(12.3456), "12.35")
        self.assertEqual(format_latex_number(12345.0, precision=0), "12,345")


if __name__ == "__main__":
    unittest.main()
