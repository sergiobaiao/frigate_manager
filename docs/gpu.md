# GPU Setup Guide

This project can use GPU acceleration for the OCR pipeline when Docker exposes an NVIDIA GPU to the backend container. Depending on the Docker Compose implementation that is installed on the host, you need to use a different snippet in your compose configuration.

## 1. Check your Docker Compose version

Run:

```bash
docker compose version
```

* Output that starts with `Docker Compose version v2` means you are running the Compose Plugin (**recommended**).
* Output that starts with `docker-compose version 1.` means you are running the legacy Compose V1 binary.

The configuration examples below show the appropriate section to add under the `backend` service in `docker-compose.yml`.

## 2. Compose Plugin (v2) configuration

Compose V2 understands [device requests](https://docs.docker.com/compose/gpu-support/) natively. Append the following block to the `backend` service:

```yaml
services:
  backend:
    device_requests:
      - driver: nvidia
        count: 1          # or "all" to pass every GPU
        capabilities: [gpu]
```

If you previously saw the error `Additional property device_requests is not allowed`, your Compose installation is still on V1—see the next section.

## 3. Legacy docker-compose (v1) configuration

Compose V1 does not support `device_requests`. Instead, use the legacy runtime flag and environment variables:

```yaml
services:
  backend:
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

When running `docker-compose`, make sure the host already has the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed, then recreate the stack:

```bash
docker-compose down
NVIDIA_VISIBLE_DEVICES=all docker-compose up -d --build --force-recreate
```

## 4. Optional Swarm deployment block

If you deploy with Docker Swarm (`docker stack deploy`), you can also add a Swarm reservation:

```yaml
services:
  backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

This block is ignored by regular Compose runs but acts as a reservation when you deploy a stack.

## 5. Verifying GPU access inside the container

After the compose stack restarts, run the following checks:

1. `docker compose exec backend nvidia-smi` (or `docker-compose exec` if you are on V1). Seeing your GPU listed confirms access.
2. Watch the backend logs for messages similar to `Falling back to easyocr ... (gpu=True)`. That line is printed when the OCR backend successfully requested GPU acceleration.

If the container still cannot see the GPU, revisit the host setup steps in the NVIDIA Container Toolkit installation guide and ensure the CUDA-enabled PyTorch wheel is installed inside the image.
