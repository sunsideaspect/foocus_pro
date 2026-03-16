# Colab Quickstart (Gradio public link)

Goal: run one Colab notebook and get a ready public Gradio URL, similar to Foocus flow.

## Option A: Open local notebook in Colab

Use `colab/Identity_Studio_Colab.ipynb`.

## Option B: Manual cells

```python
!git clone https://github.com/sunsideaspect/foocus_pro.git
%cd foocus_pro
!pip install -r colab/requirements.txt
!python -m colab.launch_colab --share --port 7860
```

After the last command, Gradio prints a public URL.

## Foocus backend compatibility modes

In Gradio UI (`Foocus Adapter` section):

- `mock` — fast local placeholder generation for smoke runs.
- `http` — calls Foocus-compatible HTTP endpoint.
- `cli` — executes Foocus CLI command.

For parity with `foocus_new`, use `http` or `cli` adapter against your Foocus runtime.
