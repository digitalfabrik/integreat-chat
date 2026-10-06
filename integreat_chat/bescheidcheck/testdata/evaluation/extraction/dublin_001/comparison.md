# Dublin decision – model comparison

Expected classification: `dublin_decision`

| Model | Classification | Extraction | Total time | Result |
|---|---|---|---:|---|
| verdigado-think | dublin_decision | Successful | 79.63 s | PASS |
| verdigado-pro | bamf_simple_rejection | Successful, but inherited wrong document type | 13.09 s | FAIL classification |
| verdigado-translate | LLM classification error / unsupported fallback | Not executed | 5.98 s | FAIL technical |

## Notes

### verdigado-think

Correctly classified the document as `dublin_decision`.

Extraction returned structured data successfully.

The phrase describing the 3-month entry/residence ban was correctly not interpreted as a deadline.

### verdigado-pro

Much faster than `verdigado-think`, but incorrectly classified the Dublin decision as `bamf_simple_rejection`.

Extraction itself produced plausible structured content, but `document_type` inherited the incorrect classification result.

### verdigado-translate

Classification failed because the LLM server returned an error.

The classifier therefore returned the fallback `unsupported`, and extraction was skipped.
