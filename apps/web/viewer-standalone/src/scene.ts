/**
 * Minimal three.js scene for the standalone offline viewer. Ported from
 * apps/web/src/viewer/sceneController.ts, trimmed to what a static deliverable viewer needs:
 * colored composite rendering + the same pan/orbit feel. No brush, no markers, no network
 * loading — every STL arrives pre-decoded as an ArrayBuffer (see base64.ts + caseData.ts).
 */
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PALETTE, STANDALONE_COLORS, type PartRole } from "./palette";
import type { CasePart } from "./caseData";
import { base64ToArrayBuffer } from "./base64";

export class StandaloneScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly loader = new STLLoader();
  private meshes: THREE.Mesh[] = [];
  private resizeObserver: ResizeObserver;
  private animationHandle = 0;
  private disposed = false;

  constructor(private readonly container: HTMLDivElement) {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(STANDALONE_COLORS.background);

    const { clientWidth, clientHeight } = container;
    this.camera = new THREE.PerspectiveCamera(
      45,
      Math.max(clientWidth, 1) / Math.max(clientHeight, 1),
      0.1,
      5000,
    );
    this.camera.position.set(0, 0, 150);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(Math.max(clientWidth, 1), Math.max(clientHeight, 1));
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    // Same pan setup as the app viewer: screen-space panning, shift+left-drag pans (right-drag
    // pan and wheel zoom are OrbitControls defaults, untouched).
    this.controls.screenSpacePanning = true;
    this.controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

    const hemi = new THREE.HemisphereLight(0xffffff, 0x1a1f1c, 1.1);
    this.scene.add(hemi);
    const dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(80, 120, 100);
    this.scene.add(dir);
    const fillDir = new THREE.DirectionalLight(0xffffff, 0.35);
    fillDir.position.set(-100, -60, -80);
    this.scene.add(fillDir);

    this.resizeObserver = new ResizeObserver(() => this.handleResize());
    this.resizeObserver.observe(container);

    window.addEventListener("keydown", this.handleShiftPanKeyDown);
    window.addEventListener("keyup", this.handleShiftPanKeyUp);
    window.addEventListener("blur", this.handleShiftPanWindowBlur);

    this.animate();
  }

  private animate = (): void => {
    if (this.disposed) return;
    this.animationHandle = requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private handleResize(): void {
    const { clientWidth, clientHeight } = this.container;
    if (clientWidth === 0 || clientHeight === 0) return;
    this.camera.aspect = clientWidth / clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(clientWidth, clientHeight);
  }

  private readonly handleShiftPanKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== "Shift") return;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  };

  private readonly handleShiftPanKeyUp = (event: KeyboardEvent): void => {
    if (event.key !== "Shift") return;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  };

  private readonly handleShiftPanWindowBlur = (): void => {
    this.controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  };

  /**
   * Replace the scene with one colored mesh per part, tinted by role (PALETTE), and frame the
   * camera on the union of their bounding boxes — the same composite-view behavior as the app.
   */
  showParts(parts: readonly CasePart[]): void {
    this.clearMeshes();

    const unionBox = new THREE.Box3();
    for (const part of parts) {
      const buffer = base64ToArrayBuffer(part.b64);
      const geometry = this.loader.parse(buffer);
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();

      const material = new THREE.MeshLambertMaterial({
        color: PALETTE[part.role],
        side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geometry, material);
      this.scene.add(mesh);
      this.meshes.push(mesh);

      if (geometry.boundingBox) {
        unionBox.union(geometry.boundingBox);
      }
    }

    this.frameOnBox3(unionBox);
  }

  private frameOnBox3(box: THREE.Box3): void {
    if (box.isEmpty()) return;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.01);

    const fovRadians = (this.camera.fov * Math.PI) / 180;
    const paddingFactor = 2.4;
    const distance = (radius * paddingFactor) / Math.sin(fovRadians / 2);

    this.controls.target.copy(center);
    const direction = new THREE.Vector3(0.4, 0.35, 1).normalize();
    this.camera.position.copy(center).addScaledVector(direction, distance);
    this.camera.near = Math.max(distance / 100, 0.01);
    this.camera.far = distance * 100;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  private clearMeshes(): void {
    for (const mesh of this.meshes) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();
      const material = mesh.material;
      if (Array.isArray(material)) {
        material.forEach((m) => m.dispose());
      } else {
        material.dispose();
      }
    }
    this.meshes = [];
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.animationHandle);
    this.resizeObserver.disconnect();
    window.removeEventListener("keydown", this.handleShiftPanKeyDown);
    window.removeEventListener("keyup", this.handleShiftPanKeyUp);
    window.removeEventListener("blur", this.handleShiftPanWindowBlur);
    this.clearMeshes();
    this.controls.dispose();
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}

export type { PartRole };
