# Dataset card: synthetic process fixtures

All measurements and limits are project-authored synthetic fixtures for software tests and bounded agent research. They are not factory records or official process limits.

| File | Purpose |
|---|---|
| batches.csv | 487 measurement rows, 63 batch IDs |
| batch_labels.json | Authored scenarios, violation/missing counts and splits |
| dataset_manifest.json | Seed, dimensions, warnings and CSV SHA-256 |
| process_sop.json | Versioned mock specifications |
| public_knowledge.json | Short attributed summaries and original URLs |
| project_handbook.json | Project-authored scope/behavior notes |
| ocr_fixture.png | Synthetic document image, no private content |

Columns include batch_id, row_id, temperature_c, pressure_mpa, viscosity_pas, device_id and measured_at. Units are Celsius, MPa and Pa·s. Row IDs remain available for citations.

The active mock SOP has inclusive ranges 180–220 °C, 1.8–2.2 MPa and 40–50 Pa·s. These are demonstration values.

## Generation and split

B-101/B-102/B-103 are hand-authored demos. The generator expands 60 batches with seed 20261020. Ten scenarios cover normal, high temperature/pressure/viscosity, multiple, missing, invalid, boundary, drift and unit-suspect measurements.

B-251–B-260 are holdout. They share the generator with development batches; there is no external real-world distribution.

~~~bash
# Deliberately rewrites fixture files; inspect the diff afterward.
uv run --frozen python -m scripts.generate_dataset
uv run --frozen python -m scripts.evaluate --split all --output runtime/evaluation/all.json
~~~

The evaluator verifies the manifest's CSV digest. Missing/invalid values remain explicit; unit-suspect values are not silently converted.

NIST/SciPy entries are short project-written summaries with original URLs. They do not replace original documentation or define acceptance limits. Third-party sources retain their terms; authored measurements, labels and mock SOP use this repository's MIT License.
