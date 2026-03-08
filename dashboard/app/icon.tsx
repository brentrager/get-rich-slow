import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: 32,
          height: 32,
          background: "#0a0a0a",
          borderRadius: 6,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
        }}
      >
        <span
          style={{
            fontSize: 24,
            fontWeight: 900,
            color: "#d4a017",
            fontFamily: "serif",
            lineHeight: 1,
          }}
        >
          R
        </span>
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: 2,
            width: 2,
            height: 28,
            marginLeft: -1,
            background: "#d4a017",
          }}
        />
      </div>
    ),
    { ...size },
  );
}
