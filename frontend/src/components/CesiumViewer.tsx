"use client";

import { useEffect, useRef } from "react";
import * as Cesium from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { API_URL } from "@/lib/api";

if (typeof window !== "undefined") {
  (window as any).CESIUM_BASE_URL = "/Cesium";
}

Cesium.Ion.defaultAccessToken = process.env.NEXT_PUBLIC_CESIUM_TOKEN || "";

// FIX: Disable ImageBitmap in Chromium browsers. It has known bugs with Cesium's 
// Texture Atlas allocation that cause text labels and points to render as static/noise boxes!
if (typeof Cesium !== "undefined" && Cesium.FeatureDetection) {
  // @ts-ignore
  (Cesium.FeatureDetection as any).supportsImageBitmapOptions = false;
}

interface CesiumViewerProps {
  tca: string;
  missDistance: number;
  riskLevel: string;
  cdmId: string;
  covarianceRadii1?: number[];
  covarianceRadii2?: number[];
}

export default function CesiumViewer({
  tca,
  missDistance,
  riskLevel,
  cdmId,
  covarianceRadii1,
  covarianceRadii2,
}: CesiumViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Cesium.Viewer | null>(null);

  useEffect(() => {
    if (!containerRef.current || viewerRef.current) return;

    // Initialize viewer
    const viewer = new Cesium.Viewer(containerRef.current, {
      terrain: Cesium.Terrain.fromWorldTerrain(),
      animation: false,
      timeline: false,
      navigationHelpButton: false,
      baseLayerPicker: false,
      homeButton: false,
      fullscreenButton: false,
      geocoder: false,
      sceneModePicker: false,
      infoBox: false,
      selectionIndicator: false,
      creditContainer: document.createElement("div"),
    });

    viewer.scene.globe.enableLighting = true;
    viewer.scene.fog.enabled = true;
    viewer.scene.requestRenderMode = false;
    viewerRef.current = viewer;

    const tcaTime = Cesium.JulianDate.fromIso8601(tca);

    // Risk colors
    const riskColors: Record<string, Cesium.Color> = {
      CRITICAL: Cesium.Color.fromCssColorString("#ff3b5c"),
      HIGH: Cesium.Color.fromCssColorString("#ff8a3d"),
      MEDIUM: Cesium.Color.fromCssColorString("#ffc233"),
      LOW: Cesium.Color.fromCssColorString("#34d399"),
    };
    const tcaColor = riskColors[riskLevel] || riskColors.CRITICAL;

    // Fetch ECEF orbit data from backend
    fetch(`${API_URL}/conjunctions/${cdmId}/orbit-data`)
      .then((res) => res.json())
      .then((data) => {
        const sat1Track = data.sat1_track || [];
        const sat2Track = data.sat2_track || [];
        const sat1Name = data.sat1_name || "SAT-1";
        const sat2Name = data.sat2_name || "SAT-2";

        // ---- SAT1: Cyan orbit ----
        if (sat1Track.length > 2) {
          const sampledPos1 = new Cesium.SampledPositionProperty();
          sampledPos1.setInterpolationOptions({
            interpolationDegree: 7,
            interpolationAlgorithm: Cesium.LagrangePolynomialApproximation,
          });

          for (const pt of sat1Track) {
            const time = Cesium.JulianDate.fromIso8601(pt.time_iso);
            const pos = new Cesium.Cartesian3(pt.x_ecef, pt.y_ecef, pt.z_ecef);
            sampledPos1.addSample(time, pos);
          }

          viewer.entities.add({
            name: sat1Name,
            position: sampledPos1,
            orientation: new Cesium.VelocityOrientationProperty(sampledPos1),
            ellipsoid: covarianceRadii1 ? {
              radii: new Cesium.Cartesian3(covarianceRadii1[0], covarianceRadii1[1], covarianceRadii1[2]),
              material: Cesium.Color.CYAN.withAlpha(0.15),
              outline: true,
              outlineColor: Cesium.Color.CYAN.withAlpha(0.6)
            } : undefined,
            point: {
              pixelSize: 6,
              color: Cesium.Color.CYAN,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
            },
            path: {
              resolution: 1,
              material: new Cesium.PolylineGlowMaterialProperty({
                glowPower: 0.2,
                color: Cesium.Color.CYAN.withAlpha(1.0),
              }),
              width: 3,
              leadTime: 5700, // 95 min ahead
              trailTime: 5700, // 95 min behind
            },
            label: {
              text: sat1Name,
              font: "11px monospace",
              fillColor: Cesium.Color.CYAN,
              style: Cesium.LabelStyle.FILL,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -12),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              showBackground: true,
              backgroundColor: Cesium.Color.BLACK.withAlpha(0.5),
              backgroundPadding: new Cesium.Cartesian2(4, 2),
            },
          });
        }

        // ---- SAT2: Red orbit ----
        if (sat2Track.length > 2) {
          const sampledPos2 = new Cesium.SampledPositionProperty();
          sampledPos2.setInterpolationOptions({
            interpolationDegree: 7,
            interpolationAlgorithm: Cesium.LagrangePolynomialApproximation,
          });

          for (const pt of sat2Track) {
            const time = Cesium.JulianDate.fromIso8601(pt.time_iso);
            const pos = new Cesium.Cartesian3(pt.x_ecef, pt.y_ecef, pt.z_ecef);
            sampledPos2.addSample(time, pos);
          }

          viewer.entities.add({
            name: sat2Name,
            position: sampledPos2,
            orientation: new Cesium.VelocityOrientationProperty(sampledPos2),
            ellipsoid: covarianceRadii2 ? {
              radii: new Cesium.Cartesian3(covarianceRadii2[0], covarianceRadii2[1], covarianceRadii2[2]),
              material: Cesium.Color.fromCssColorString("#ff3b5c").withAlpha(0.15),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString("#ff3b5c").withAlpha(0.6)
            } : undefined,
            point: {
              pixelSize: 6,
              color: Cesium.Color.fromCssColorString("#ff3b5c"),
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
            },
            path: {
              resolution: 1,
              material: new Cesium.PolylineGlowMaterialProperty({
                glowPower: 0.2,
                color: Cesium.Color.fromCssColorString("#ff3b5c").withAlpha(1.0),
              }),
              width: 3,
              leadTime: 5700,
              trailTime: 5700,
            },
            label: {
              text: sat2Name,
              font: "11px monospace",
              fillColor: Cesium.Color.fromCssColorString("#ff8fa3"),
              style: Cesium.LabelStyle.FILL,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -12),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              showBackground: true,
              backgroundColor: Cesium.Color.BLACK.withAlpha(0.5),
              backgroundPadding: new Cesium.Cartesian2(4, 2),
            },
          });
        }

        // ---- TCA Marker: pulsing sphere ----
        if (data.tca_position_ecef) {
          const tcaPos = new Cesium.Cartesian3(
            data.tca_position_ecef.x,
            data.tca_position_ecef.y,
            data.tca_position_ecef.z
          );

          let isHighlight = false;
          let hasZoomedIn = false;
          let hasZoomedOut = false;

          viewer.clock.onTick.addEventListener((clock) => {
            const secondsFromTCA = Math.abs(Cesium.JulianDate.secondsDifference(clock.currentTime, tcaTime));
            isHighlight = secondsFromTCA < 60;

            // Close-approach auto-zoom — zoom in when near TCA
            if (secondsFromTCA < 30 && !hasZoomedIn) {
              hasZoomedIn = true;
              hasZoomedOut = false;
              const dir = Cesium.Cartesian3.normalize(tcaPos, new Cesium.Cartesian3());
              const closeUp = Cesium.Cartesian3.multiplyByScalar(
                dir, Cesium.Cartesian3.magnitude(tcaPos) + 200000, new Cesium.Cartesian3()
              );
              viewer.camera.flyTo({ destination: closeUp, duration: 1.0 });
            }
            // Pull back out after TCA passage
            if (secondsFromTCA > 120 && hasZoomedIn && !hasZoomedOut) {
              hasZoomedOut = true;
              const dir = Cesium.Cartesian3.normalize(tcaPos, new Cesium.Cartesian3());
              const pullBack = Cesium.Cartesian3.multiplyByScalar(
                dir, Cesium.Cartesian3.magnitude(tcaPos) + 3000000, new Cesium.Cartesian3()
              );
              viewer.camera.flyTo({ destination: pullBack, duration: 1.5 });
            }
          });

          const tcaEntity = viewer.entities.add({
            position: tcaPos,
            point: {
              pixelSize: new Cesium.CallbackProperty(() => isHighlight ? 30 : 15, false),
              color: new Cesium.CallbackProperty(() => isHighlight ? Cesium.Color.WHITE : tcaColor, false),
              outlineColor: Cesium.Color.BLACK,
              outlineWidth: 2,
            },
            label: {
              text: `TCA · ${missDistance.toFixed(0)}m`,
              font: "11px monospace",
              fillColor: Cesium.Color.WHITE,
              verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
              pixelOffset: new Cesium.Cartesian2(0, -25),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              showBackground: true,
              backgroundColor: Cesium.Color.BLACK.withAlpha(0.6),
              backgroundPadding: new Cesium.Cartesian2(6, 3),
            },
          });

          // ---- Miss-Distance Connector Line ----
          if (data.sat2_tca_position_ecef) {
            const tcaPos2 = new Cesium.Cartesian3(
              data.sat2_tca_position_ecef.x,
              data.sat2_tca_position_ecef.y,
              data.sat2_tca_position_ecef.z
            );

            // Dashed connector line between SAT1 and SAT2 at TCA
            viewer.entities.add({
              name: "Miss Distance",
              polyline: {
                positions: [tcaPos, tcaPos2],
                width: 2,
                material: new Cesium.PolylineDashMaterialProperty({
                  color: tcaColor.withAlpha(0.9),
                  dashLength: 12.0,
                }),
                depthFailMaterial: new Cesium.PolylineDashMaterialProperty({
                  color: tcaColor.withAlpha(0.4),
                  dashLength: 12.0,
                }),
              },
            });

            // Midpoint label showing the miss distance
            const midpoint = Cesium.Cartesian3.midpoint(tcaPos, tcaPos2, new Cesium.Cartesian3());
            viewer.entities.add({
              position: midpoint,
              label: {
                text: missDistance < 1000
                  ? `${missDistance.toFixed(0)} m`
                  : `${(missDistance / 1000).toFixed(1)} km`,
                font: "10px monospace",
                fillColor: tcaColor,
                style: Cesium.LabelStyle.FILL,
                pixelOffset: new Cesium.Cartesian2(0, -8),
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
                showBackground: true,
                backgroundColor: Cesium.Color.BLACK.withAlpha(0.7),
                backgroundPadding: new Cesium.Cartesian2(5, 2),
                scale: 0.9,
              },
            });
          }

          // Camera: zoom to see full orbit
          const flyToTCA = () => {
             const direction = Cesium.Cartesian3.normalize(tcaPos, new Cesium.Cartesian3());
             const destination = Cesium.Cartesian3.multiplyByScalar(direction, Cesium.Cartesian3.magnitude(tcaPos) + 3000000, new Cesium.Cartesian3());
             viewer.camera.flyTo({ 
               destination: destination, 
               duration: 1.5 
             });
          };
          flyToTCA();
          
          // Expose function for UI button
          (window as any).focusTCA = flyToTCA;
        }

        // ---- Clock: animate along orbit ----
        if (sat1Track.length > 2) {
          const startTime = Cesium.JulianDate.fromIso8601(sat1Track[0].time_iso);
          const endTime = Cesium.JulianDate.fromIso8601(sat1Track[sat1Track.length - 1].time_iso);
          viewer.clock.startTime = startTime;
          viewer.clock.stopTime = endTime;
          viewer.clock.currentTime = Cesium.JulianDate.addMinutes(tcaTime, -5, new Cesium.JulianDate());
          viewer.clock.clockRange = Cesium.ClockRange.LOOP_STOP;
          viewer.clock.multiplier = 120; // 2 min per second
          viewer.clock.shouldAnimate = true;
        }

        // ---- Astrodynamics Showcase: Ghost Orbit Projection ----
        let ghostEntity: Cesium.Entity | null = null;
        const updateGhostOrbit = (offsetAmount: number) => {
           if (ghostEntity) {
             viewer.entities.remove(ghostEntity);
             ghostEntity = null;
           }
           if (!offsetAmount || offsetAmount === 0 || sat1Track.length < 2) return;

           const ghostPos = new Cesium.SampledPositionProperty();
           ghostPos.setInterpolationOptions({
             interpolationDegree: 7,
             interpolationAlgorithm: Cesium.LagrangePolynomialApproximation,
           });

           for (let i = 0; i < sat1Track.length - 1; i++) {
             const p1 = sat1Track[i];
             const p2 = sat1Track[i + 1];
             const t1 = new Date(p1.time_iso).getTime();
             const t2 = new Date(p2.time_iso).getTime();
             const dt = (t2 - t1) / 1000.0;
             if (dt === 0) continue;

             const vx = (p2.x_ecef - p1.x_ecef) / dt;
             const vy = (p2.y_ecef - p1.y_ecef) / dt;
             const vz = (p2.z_ecef - p1.z_ecef) / dt;

             const v_mag = Math.sqrt(vx * vx + vy * vy + vz * vz);
             if (v_mag === 0) continue;

             // Map the along-track spatial offset using the tangent trace
             const gx = p1.x_ecef + (vx / v_mag) * offsetAmount;
             const gy = p1.y_ecef + (vy / v_mag) * offsetAmount;
             const gz = p1.z_ecef + (vz / v_mag) * offsetAmount;

             ghostPos.addSample(Cesium.JulianDate.fromIso8601(p1.time_iso), new Cesium.Cartesian3(gx, gy, gz));
           }

           ghostEntity = viewer.entities.add({
             name: "Predictive Trajectory Override",
             position: ghostPos,
             path: {
               resolution: 1,
               material: new Cesium.PolylineDashMaterialProperty({
                 color: Cesium.Color.fromCssColorString("#4ade80").withAlpha(0.8), // neon green
                 dashLength: 30.0,
               }),
               width: 4,
               leadTime: 5700,
               trailTime: 5700,
             },
           });
        };

        const handleGhostEvent = (e: any) => updateGhostOrbit(e.detail);
        window.addEventListener("updateGhostOrbit", handleGhostEvent);
        (window as any).__conjunxGhostHandler = handleGhostEvent;
      })
      .catch((err) => {
        console.warn("Orbit data fetch failed:", err);
      });

    return () => {
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
         try { viewerRef.current.destroy(); } catch(e){}
      }
      viewerRef.current = null;
      if ((window as any).focusTCA) delete (window as any).focusTCA;
      if ((window as any).__conjunxGhostHandler) {
         window.removeEventListener("updateGhostOrbit", (window as any).__conjunxGhostHandler);
         delete (window as any).__conjunxGhostHandler;
      }
    };
  }, [tca, missDistance, riskLevel, cdmId, covarianceRadii1, covarianceRadii2]);

  return (
    <div className="relative w-full h-full min-h-[400px]">
      <div ref={containerRef} className="absolute inset-0" />
      <button 
        onClick={() => { if ((window as any).focusTCA) (window as any).focusTCA(); }}
        className="absolute bottom-3 left-3 z-10 px-3 py-1.5 bg-[#161b22] border border-[#30363d] text-[11px] font-data text-[#7d8590] hover:bg-[#1c2128] hover:text-[#e6edf3] transition-colors uppercase tracking-wider"
      >
        Focus TCA
      </button>
    </div>
  );
}
