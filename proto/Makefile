PROTO_DIRS  := common/v1 client/v1 vad/v1 inference/v1
PY_OUT      := gen/python/stt_proto
PYTHON      ?= ../.venv/bin/python3
PROTOC      ?= protoc
GO          ?= go
GOBIN       ?= $(HOME)/go/bin

.PHONY: generate generate-go generate-python lint clean

generate: generate-go generate-python

generate-go:
	@mkdir -p gen/go
	@for dir in $(PROTO_DIRS); do \
		echo "  [go] $$dir"; \
		PATH="$(GOBIN):$$PATH" $(PROTOC) \
			-I. \
			--go_out=gen/go --go_opt=paths=source_relative \
			--go-grpc_out=gen/go --go-grpc_opt=paths=source_relative \
			$$dir/*.proto; \
	done

generate-python:
	@mkdir -p $(PY_OUT)
	@for dir in $(PROTO_DIRS); do \
		echo "  [python] $$dir"; \
		$(PYTHON) -m grpc_tools.protoc \
			-I. \
			--python_out=$(PY_OUT) \
			--grpc_python_out=$(PY_OUT) \
			--pyi_out=$(PY_OUT) \
			$$dir/*.proto; \
	done
	@$(MAKE) _fix-python-imports _ensure-python-inits

# grpcio-tools generates bare "from common.v1 import …" imports.
# Patch them to be rooted under the stt_proto namespace package.
_fix-python-imports:
	@echo "  [python] fixing imports in $(PY_OUT)"
	@find $(PY_OUT) -name "*_pb2*.py" -o -name "*_pb2*.pyi" | while read f; do \
		sed -i.bak \
			-e 's/^from common\.v1 /from stt_proto.common.v1 /g' \
			-e 's/^from client\.v1 /from stt_proto.client.v1 /g' \
			-e 's/^from vad\.v1 /from stt_proto.vad.v1 /g' \
			-e 's/^from inference\.v1 /from stt_proto.inference.v1 /g' \
			-e 's/^import common\.v1/import stt_proto.common.v1/g' \
			"$$f" && rm -f "$$f.bak"; \
	done

# Make sure every generated subdirectory has an __init__.py.
_ensure-python-inits:
	@find $(PY_OUT) -type d -exec touch {}/__init__.py \;

lint:
	@which buf > /dev/null 2>&1 && buf lint || echo "buf not installed, skipping lint"

clean:
	rm -rf gen/go gen/python/stt_proto
