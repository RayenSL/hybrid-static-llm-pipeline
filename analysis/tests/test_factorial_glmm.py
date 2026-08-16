import unittest

import pandas as pd

import analysis.factorial_glmm as glmm


class FactorialGlmmTests(unittest.TestCase):
    def test_validation_accepts_624_rows_and_26_instances(self):
        validate = getattr(glmm, "validate_model_ready_data", None)
        self.assertIsNotNone(validate, "dynamic GLMM design validation is not implemented")
        data = pd.DataFrame({
            "instance_id": [instance for instance in range(1, 27) for _ in range(24)]
        })

        observations, instances = validate(data)

        self.assertEqual(624, observations)
        self.assertEqual(26, instances)


if __name__ == "__main__":
    unittest.main()
