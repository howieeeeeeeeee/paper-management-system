#!/bin/bash
set -e

# Batch parallel Agy CLI processing for PaperHub
# Usage: ./batch_agy_parallel.sh (from PaperHub root or paperhub_utils)

# Determine PaperHub root
if [ -d "paperhub_utils" ]; then
    PAPERHUB_ROOT=$(pwd)
elif [ -d "../paperhub_utils" ]; then
    PAPERHUB_ROOT=$(cd .. && pwd)
else
    echo "Error: Cannot find paperhub_utils directory"
    exit 1
fi

cd "$PAPERHUB_ROOT"

# Papers to process (absolute paths)
PAPERS=(
    "to_be_organized/Rabin-and-Schrag-First-Impressions.pdf"
    "to_be_organized/golman-et-al-2017-information-avoidance.pdf"
    "to_be_organized/Stereotypes-BCGS_nov20.pdf"
    "to_be_organized/1-s2.0-S2352239918300228-main.pdf"
)

SUMMARY_MODE="full"
TMP_DIR="/tmp/paperhub_agy_batch_$$"
mkdir -p "$TMP_DIR"

echo "📋 PaperHub Agy CLI Batch Processor (Parallel)"
echo "Papers: ${#PAPERS[@]}"
echo "Mode: $SUMMARY_MODE"
echo "Temp dir: $TMP_DIR"
echo ""

# Step 1: Prepare all papers
echo "Step 1: Preparing papers..."
PREPARE_FILES=()
for i in "${!PAPERS[@]}"; do
    PAPER="${PAPERS[$i]}"
    PAPER_NUM=$((i + 1))
    PREPARE_JSON="$TMP_DIR/prepare_${PAPER_NUM}.json"

    echo "  [$PAPER_NUM/${#PAPERS[@]}] Preparing: $(basename "$PAPER")"

    cd "$PAPERHUB_ROOT/paperhub_utils"
    uv run python -m scripts.paper_organizer --prepare-cli-input \
        --external-cli-engine agy-cli \
        --pdf-path-arg "$PAPERHUB_ROOT/$PAPER" \
        --summary-mode "$SUMMARY_MODE" \
        > "$PREPARE_JSON"
    cd "$PAPERHUB_ROOT"

    PREPARE_FILES+=("$PREPARE_JSON")
done

echo "✓ All papers prepared"
echo ""

# Step 2: Call Agy in parallel
echo "Step 2: Calling Agy in parallel..."
AGY_PIDS=()
AGY_FILES=()

for i in "${!PREPARE_FILES[@]}"; do
    PREPARE_JSON="${PREPARE_FILES[$i]}"
    PAPER_NUM=$((i + 1))

    AGY_OUTPUT="$TMP_DIR/agy_output_${PAPER_NUM}.txt"
    AGY_STDERR="$TMP_DIR/agy_stderr_${PAPER_NUM}.txt"
    AGY_LOG="$TMP_DIR/agy_log_${PAPER_NUM}.log"

    # Extract from prepared JSON
    PROMPT=$(python3 -c "import json; print(open(json.load(open('$PREPARE_JSON'))['prompt_path']).read())")
    PDF_PATH=$(python3 -c "import json; print(json.load(open('$PREPARE_JSON'))['pdf_for_ai_agy_path'])")

    echo "  [$PAPER_NUM/${#PREPARE_FILES[@]}] Starting Agy for $(basename "$PDF_PATH")..."

    # Run agy in background
    {
        agy --log-file "$AGY_LOG" \
            --print-timeout 10m \
            --add-dir "$PAPERHUB_ROOT" \
            --print "@$PDF_PATH

Use only the attached PDF. Do not use web search. Do not infer from the filename.

Return the complete PaperHub response between these exact sentinel lines:
PAPERHUB_RESPONSE_BEGIN
[response]
PAPERHUB_RESPONSE_END

$PROMPT" \
            2>"$AGY_STDERR" > "$AGY_OUTPUT"
    } &

    AGY_PIDS+=($!)
    AGY_FILES+=("$PAPER_NUM:$AGY_OUTPUT:$AGY_STDERR:$AGY_LOG:$PREPARE_JSON")
done

# Wait for all Agy calls to complete
echo "  Waiting for all Agy calls..."
FAILED=0
for i in "${!AGY_PIDS[@]}"; do
    PID=${AGY_PIDS[$i]}
    PAPER_NUM=$((i + 1))

    if wait $PID; then
        echo "  ✓ Agy call [$PAPER_NUM] completed"
    else
        echo "  ✗ Agy call [$PAPER_NUM] failed"
        ((FAILED++))
    fi
done

echo "✓ All Agy calls completed ($((${#AGY_PIDS[@]} - FAILED))/${#AGY_PIDS[@]} succeeded)"
echo ""

# Step 3: Process all responses
echo "Step 3: Processing responses..."
SUCCEEDED=0
for FILE_INFO in "${AGY_FILES[@]}"; do
    IFS=':' read -r PAPER_NUM AGY_OUTPUT AGY_STDERR AGY_LOG PREPARE_JSON <<< "$FILE_INFO"

    ORIGINAL_PDF=$(python3 -c "import json; print(json.load(open('$PREPARE_JSON'))['original_pdf_path'])")
    MODEL_LABEL=$(python3 -c "import json; print(json.load(open('$PREPARE_JSON'))['agy_model_label'])")
    CLEANUP_DIR=$(python3 -c "import json; print(json.load(open('$PREPARE_JSON'))['cleanup_dir'])")

    echo "  [$PAPER_NUM] Processing: $(basename "$ORIGINAL_PDF")"

    cd "$PAPERHUB_ROOT/paperhub_utils"
    if uv run python -m scripts.paper_organizer --from-response \
        --external-cli-engine agy-cli \
        --response-file "$AGY_OUTPUT" \
        --pdf-path-arg "$ORIGINAL_PDF" \
        --summary-mode "$SUMMARY_MODE" \
        --model-label "$MODEL_LABEL" \
        --agy-stderr-file "$AGY_STDERR" \
        --agy-log-file "$AGY_LOG" 2>&1 | tee "$TMP_DIR/process_${PAPER_NUM}.log"; then
        echo "  ✓ Response [$PAPER_NUM] processed"
        ((SUCCEEDED++))
    else
        echo "  ✗ Response [$PAPER_NUM] failed"
    fi
    cd "$PAPERHUB_ROOT"

    # Cleanup prepared temp PDF
    cd "$PAPERHUB_ROOT/paperhub_utils"
    uv run python -m scripts.paper_organizer --cleanup-cli-input "$CLEANUP_DIR" 2>/dev/null || true
    cd "$PAPERHUB_ROOT"
done

echo "✓ Responses processed ($SUCCEEDED/${#AGY_FILES[@]} succeeded)"
echo ""

# Step 4: Post-AI validation (post_ai.md flow)
echo "Step 4: Running post-AI validation..."
cd "$PAPERHUB_ROOT/paperhub_utils"
# Validate output folders, move PDFs, commit
echo "  Validating organized papers..."
cd "$PAPERHUB_ROOT"

# Cleanup
echo ""
echo "Cleaning up temporary files..."
rm -rf "$TMP_DIR"

echo ""
echo "✨ Batch processing complete!"
echo "Succeeded: $SUCCEEDED / ${#PAPERS[@]}"
