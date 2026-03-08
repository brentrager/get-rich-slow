import { ImageResponse } from "next/og";

export const alt = "Rager's Get Rich Slow Scheme";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function TwitterImage() {
    return new ImageResponse(
        (
            <div
                style={{
                    width: "100%",
                    height: "100%",
                    background: "linear-gradient(135deg, #0a0a0a 0%, #1a1a0a 50%, #0a0a0a 100%)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    position: "relative",
                    overflow: "hidden",
                }}
            >
                {/* Gold border glow */}
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        border: "3px solid #d4a017",
                        borderRadius: 0,
                        display: "flex",
                    }}
                />
                <div
                    style={{
                        position: "absolute",
                        inset: 8,
                        border: "1px solid #8b6914",
                        display: "flex",
                    }}
                />

                {/* Large R with vertical strikethrough */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        position: "relative",
                        marginBottom: 20,
                    }}
                >
                    <span
                        style={{
                            fontSize: 180,
                            fontWeight: 900,
                            color: "#d4a017",
                            fontFamily: "serif",
                            lineHeight: 1,
                            textShadow: "0 0 40px rgba(212, 160, 23, 0.5)",
                        }}
                    >
                        R
                    </span>
                    <div
                        style={{
                            position: "absolute",
                            left: "50%",
                            top: -10,
                            width: 6,
                            height: 200,
                            marginLeft: -3,
                            background:
                                "linear-gradient(180deg, transparent 0%, #f0d060 20%, #d4a017 50%, #f0d060 80%, transparent 100%)",
                            borderRadius: 3,
                            display: "flex",
                        }}
                    />
                </div>

                {/* Title */}
                <div
                    style={{
                        fontSize: 64,
                        fontWeight: 900,
                        background: "linear-gradient(90deg, #8b6914, #f0d060, #d4a017, #f0d060, #8b6914)",
                        backgroundClip: "text",
                        color: "transparent",
                        letterSpacing: "-2px",
                        display: "flex",
                    }}
                >
                    Rager's Get Rich Slow Scheme
                </div>

                {/* Subtitle */}
                <div
                    style={{
                        fontSize: 28,
                        color: "#8b6914",
                        marginTop: 16,
                        letterSpacing: 6,
                        textTransform: "uppercase",
                        display: "flex",
                    }}
                >
                    Kalshi Sports Market Scanner
                </div>

                {/* Bottom accent line */}
                <div
                    style={{
                        position: "absolute",
                        bottom: 40,
                        width: 200,
                        height: 2,
                        background: "linear-gradient(90deg, transparent, #d4a017, transparent)",
                        display: "flex",
                    }}
                />
            </div>
        ),
        { ...size },
    );
}
