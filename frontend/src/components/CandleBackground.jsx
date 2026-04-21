import { useEffect, useRef } from "react";

// Top NSE companies with their colors
const COMPANIES = [
    { sym: "RELIANCE",   color: "#4f9eff", domain: "ril.com"           },
    { sym: "TCS",        color: "#00e676", domain: "tcs.com"           },
    { sym: "INFY",       color: "#ffd54f", domain: "infosys.com"       },
    { sym: "HDFCBANK",   color: "#4f9eff", domain: "hdfcbank.com"      },
    { sym: "ICICIBANK",  color: "#00e676", domain: "icicibank.com"     },
    { sym: "WIPRO",      color: "#ff8a65", domain: "wipro.com"         },
    { sym: "TATAMOTORS", color: "#ce93d8", domain: "tatamotors.com"    },
    { sym: "SBIN",       color: "#4f9eff", domain: "sbi.co.in"         },
    { sym: "MARUTI",     color: "#ffd54f", domain: "marutisuzuki.com"  },
    { sym: "HCLTECH",    color: "#00e676", domain: "hcltech.com"       },
    { sym: "ADANIENT",   color: "#ff5252", domain: "adani.com"         },
    { sym: "BHARTIARTL", color: "#4f9eff", domain: "airtel.in"         },
    { sym: "KOTAKBANK",  color: "#ce93d8", domain: "kotak.com"         },
    { sym: "LT",         color: "#ffd54f", domain: "larsentoubro.com"  },
    { sym: "BAJFINANCE", color: "#00e676", domain: "bajajfinserv.in"   },
    { sym: "NTPC",       color: "#ff8a65", domain: "ntpc.co.in"        },
    { sym: "SUNPHARMA",  color: "#4f9eff", domain: "sunpharma.com"     },
    { sym: "ASIANPAINT", color: "#ce93d8", domain: "asianpaints.com"   },
    { sym: "TITAN",      color: "#ffd54f", domain: "titancompany.in"   },
    { sym: "TECHM",      color: "#00e676", domain: "techm.com"         },
];

export default function CandleBackground() {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        const ctx    = canvas.getContext("2d");
        let   animId = null;

        const getVar = (v) =>
            getComputedStyle(document.documentElement).getPropertyValue(v).trim();

        const resize = () => {
            canvas.width  = window.innerWidth;
            canvas.height = window.innerHeight;
        };
        resize();
        window.addEventListener("resize", resize);

        function rgba(hex, a) {
            const h = hex.replace("#","");
            const r = parseInt(h.slice(0,2),16);
            const g = parseInt(h.slice(2,4),16);
            const b = parseInt(h.slice(4,6),16);
            return `rgba(${r},${g},${b},${a})`;
        }

        // ── Pre-load company logos ───────────────────────────────
        const logoCache = {};
        COMPANIES.forEach(c => {
            const img = new Image();
            img.crossOrigin = "anonymous";
            img.src = `https://logo.clearbit.com/${c.domain}`;
            img.onload  = () => { logoCache[c.sym] = img; };
            img.onerror = () => { logoCache[c.sym] = null; };
        });

        // ── Floating ticker cards ────────────────────────────────
        // Each card has: company, a mini candle chart, price, change
        function makeTicker(x, y) {
            const co     = COMPANIES[Math.floor(Math.random() * COMPANIES.length)];
            const change = (Math.random() - 0.46) * 4.5;
            const price  = 500 + Math.random() * 3500;
            // mini candle data for sparkline
            const spark  = Array.from({ length: 18 }, (_, i) => {
                const v = 50 + Math.sin(i * 0.5 + Math.random()) * 20 + Math.random() * 10;
                return v;
            });
            return {
                x, y,
                vx: -0.35 - Math.random() * 0.25,
                vy: (Math.random() - 0.5) * 0.08,
                co, change, price, spark,
                alpha: 0,        // fade in
                fadeIn:  true,
                fadeOut: false,
                life:    0,
                maxLife: 420 + Math.random() * 300,
                w: 148, h: 70,
            };
        }

        // Seed initial tickers spread across screen
        const tickers = Array.from({ length: 10 }, () =>
            makeTicker(
                Math.random() * canvas.width,
                canvas.height * 0.08 + Math.random() * canvas.height * 0.84
            )
        );
        // Stagger their life so they don't all die at once
        tickers.forEach((t, i) => { t.life = i * 60; });

        // ── Draw one ticker card ─────────────────────────────────
        function drawTicker(tk, upColor, downColor) {
            const { x, y, co, change, price, spark, alpha, w, h } = tk;
            const isUp   = change >= 0;
            const accent = isUp ? upColor : downColor;
            if (alpha <= 0) return;

            ctx.save();
            ctx.globalAlpha = alpha;

            // Card background
            const bgHex = getVar("--bg-secondary") || "#0d1526";
            const cardGrad = ctx.createLinearGradient(x, y, x + w, y + h);
            cardGrad.addColorStop(0, rgba(bgHex, 0.82));
            cardGrad.addColorStop(1, rgba(bgHex, 0.65));
            ctx.fillStyle = cardGrad;
            ctx.beginPath();
            ctx.roundRect(x, y, w, h, 10);
            ctx.fill();

            // Card border — accent color
            ctx.strokeStyle = rgba(co.color, 0.45);
            ctx.lineWidth   = 1;
            ctx.beginPath();
            ctx.roundRect(x, y, w, h, 10);
            ctx.stroke();

            // Left accent bar
            ctx.fillStyle = rgba(co.color, 0.8);
            ctx.beginPath();
            ctx.roundRect(x, y + 8, 3, h - 16, 2);
            ctx.fill();

            // Company logo or initials
            const logoImg = logoCache[co.sym];
            const logoSize = 22;
            const lx = x + 12, ly = y + 10;
            if (logoImg) {
                ctx.save();
                ctx.beginPath();
                ctx.roundRect(lx, ly, logoSize, logoSize, 5);
                ctx.clip();
                ctx.drawImage(logoImg, lx, ly, logoSize, logoSize);
                ctx.restore();
            } else {
                ctx.fillStyle   = rgba(co.color, 0.25);
                ctx.beginPath();
                ctx.roundRect(lx, ly, logoSize, logoSize, 5);
                ctx.fill();
                ctx.fillStyle   = co.color;
                ctx.font        = `bold 9px 'DM Sans', sans-serif`;
                ctx.textAlign   = "center";
                ctx.textBaseline= "middle";
                ctx.fillText(co.sym.slice(0,3), lx + logoSize/2, ly + logoSize/2);
            }

            // Symbol name
            ctx.fillStyle   = getVar("--text-primary") || "#e8f0fe";
            ctx.font        = `bold 11px 'Syne', sans-serif`;
            ctx.textAlign   = "left";
            ctx.textBaseline= "middle";
            ctx.fillText(co.sym, lx + logoSize + 6, ly + logoSize / 2 - 2);

            // Exchange tag
            ctx.fillStyle = rgba(co.color, 0.65);
            ctx.font      = `10px 'JetBrains Mono', monospace`;
            ctx.fillText("NSE", lx + logoSize + 6, ly + logoSize / 2 + 9);

            // Price
            ctx.fillStyle   = getVar("--text-primary") || "#e8f0fe";
            ctx.font        = `bold 13px 'JetBrains Mono', monospace`;
            ctx.textAlign   = "left";
            ctx.fillText(`₹${price.toFixed(0)}`, x + 12, y + h - 22);

            // Change badge
            const badgeX = x + 12 + ctx.measureText(`₹${price.toFixed(0)}`).width + 6;
            ctx.fillStyle = rgba(accent, 0.18);
            ctx.beginPath();
            ctx.roundRect(badgeX - 2, y + h - 29, 52, 16, 4);
            ctx.fill();
            ctx.fillStyle = accent;
            ctx.font      = `bold 9px 'JetBrains Mono', monospace`;
            ctx.fillText(`${isUp ? "▲" : "▼"} ${Math.abs(change).toFixed(2)}%`, badgeX + 2, y + h - 22);

            // ── Mini sparkline candle chart ──────────────────────
            const chartX  = x + w - 58;
            const chartY  = y + 10;
            const chartW  = 50;
            const chartH  = h - 20;
            const cw      = 4, gap = 1;
            const minV    = Math.min(...spark);
            const maxV    = Math.max(...spark);
            const range   = maxV - minV || 1;

            spark.forEach((v, i) => {
                const bx   = chartX + i * (cw + gap);
                const by   = chartY + chartH - ((v - minV) / range) * chartH;
                const bh   = Math.max(2, ((v - minV) / range) * chartH * 0.6);
                const cUp  = v > (spark[i - 1] || v);
                const col  = cUp ? upColor : downColor;
                ctx.fillStyle   = rgba(col, 0.55);
                ctx.strokeStyle = rgba(col, 0.8);
                ctx.lineWidth   = 0.5;
                ctx.fillRect(bx, by, cw, bh);
                ctx.strokeRect(bx, by, cw, bh);
            });

            ctx.restore();
        }

        // ── Background candle stream ─────────────────────────────
        // Large slow candles scrolling across the full height
        const BIG_W  = 18;
        const BIG_GAP= 10;
        const PITCH  = BIG_W + BIG_GAP;
        const NCOLS  = Math.ceil(canvas.width / PITCH) + 4;

        function makeBigCandle(x) {
            const cy = canvas.height * (0.2 + Math.random() * 0.6);
            const r  = canvas.height * 0.08;
            const o  = cy + (Math.random() - 0.5) * r;
            const c  = o  + (Math.random() - 0.48) * r * 0.7;
            const w  = r * 0.4;
            return {
                x, open: o, close: c,
                high: Math.min(o,c) - Math.random() * w,
                low:  Math.max(o,c) + Math.random() * w,
                isUp: c <= o,
            };
        }

        const bgCandles = Array.from({ length: NCOLS }, (_, i) =>
            makeBigCandle(i * PITCH)
        );

        function drawBgCandles(upColor, downColor) {
            bgCandles.forEach(c => {
                const col   = c.isUp ? upColor : downColor;
                const bTop  = Math.min(c.open, c.close);
                const bH    = Math.max(Math.abs(c.close - c.open), 2);
                const cx    = c.x + BIG_W / 2;

                ctx.strokeStyle = rgba(col, 0.12);
                ctx.lineWidth   = 1;
                ctx.beginPath();
                ctx.moveTo(cx, c.high);
                ctx.lineTo(cx, c.low);
                ctx.stroke();

                ctx.fillStyle   = rgba(col, 0.07);
                ctx.strokeStyle = rgba(col, 0.13);
                ctx.lineWidth   = 0.5;
                ctx.fillRect(c.x, bTop, BIG_W, bH);
                ctx.strokeRect(c.x, bTop, BIG_W, bH);
            });

            bgCandles.forEach(c => { c.x -= 0.22; });
            if (bgCandles[0].x < -PITCH) {
                bgCandles.shift();
                bgCandles.push(makeBigCandle(bgCandles[bgCandles.length-1].x + PITCH));
            }
        }

        // ── Vignette ─────────────────────────────────────────────
        function drawVignette(bgColor) {
            const top = ctx.createLinearGradient(0, 0, 0, canvas.height * 0.16);
            top.addColorStop(0, rgba(bgColor, 0.26));
            top.addColorStop(1, "transparent");
            ctx.fillStyle = top;
            ctx.fillRect(0, 0, canvas.width, canvas.height * 0.16);

            const bottom = ctx.createLinearGradient(0, canvas.height * 0.78, 0, canvas.height);
            bottom.addColorStop(0, "transparent");
            bottom.addColorStop(1, rgba(bgColor, 0.30));
            ctx.fillStyle = bottom;
            ctx.fillRect(0, canvas.height * 0.78, canvas.width, canvas.height * 0.22);

            const left = ctx.createLinearGradient(0, 0, canvas.width * 0.04, 0);
            left.addColorStop(0, rgba(bgColor, 0.16));
            left.addColorStop(1, "transparent");
            ctx.fillStyle = left;
            ctx.fillRect(0, 0, canvas.width * 0.04, canvas.height);

            const right = ctx.createLinearGradient(canvas.width * 0.96, 0, canvas.width, 0);
            right.addColorStop(0, "transparent");
            right.addColorStop(1, rgba(bgColor, 0.16));
            ctx.fillStyle = right;
            ctx.fillRect(canvas.width * 0.96, 0, canvas.width * 0.04, canvas.height);
        }

        // ── Main loop ────────────────────────────────────────────
        let t = 0;
        function draw() {
            t++;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.shadowBlur = 0;

            const upColor   = getVar("--accent-up")   || "#00e676";
            const downColor = getVar("--accent-down")  || "#ff5252";
            const bgColor   = getVar("--bg-primary")   || "#060b18";

            // 1 — background candles
            drawBgCandles(upColor, downColor);

            // 2 — ticker cards
            tickers.forEach(tk => {
                // Lifecycle
                tk.life++;
                tk.x += tk.vx;
                tk.y += tk.vy;

                if (tk.fadeIn) {
                    tk.alpha = Math.min(tk.alpha + 0.025, 0.92);
                    if (tk.alpha >= 0.92) tk.fadeIn = false;
                }
                if (tk.life > tk.maxLife) tk.fadeOut = true;
                if (tk.fadeOut) {
                    tk.alpha = Math.max(tk.alpha - 0.018, 0);
                    if (tk.alpha <= 0) {
                        // respawn off-screen right
                        Object.assign(tk, makeTicker(
                            canvas.width + 160,
                            canvas.height * 0.08 + Math.random() * canvas.height * 0.84
                        ));
                    }
                }

                drawTicker(tk, upColor, downColor);
            });

            // 3 — vignette
            drawVignette(bgColor);

            animId = requestAnimationFrame(draw);
        }

        draw();

        return () => {
            window.removeEventListener("resize", resize);
            if (animId) cancelAnimationFrame(animId);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            style={{
                position: "absolute",
                inset:    0,
                width:    "100%",
                height:   "100%",
                zIndex:   0,
            }}
        />
    );
}
