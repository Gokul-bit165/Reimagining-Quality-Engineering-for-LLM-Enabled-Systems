"""Inline CSS/JS for the static viewer. Tokens documented in bench/results/p1/DESIGN.md."""

CSS = """
:root{--paper:#f7f5ef;--ink:#1c1b18;--muted:#55524a;--rule:#cfc9ba;--notrun:#efece3;
--release:#1d6a38;--reject:#a2281c;--insufficient:#7a5200;--conditional:#1f4f8f;
--s1:.25rem;--s2:.5rem;--s3:1rem;--s4:1.5rem;--s5:2.5rem;--s6:4rem;
--display:Georgia,"Iowan Old Style",serif;--text:system-ui,-apple-system,"Segoe UI",sans-serif;
--data:ui-monospace,"Cascadia Mono",Consolas,monospace}
*{box-sizing:border-box}
html{font-size:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:.9375rem/1.55 var(--text)}
.page{max-width:72rem;margin:0 auto;padding:var(--s4) var(--s3) var(--s6)}
main{max-width:46rem}
nav ol{list-style:none;margin:0 0 var(--s4);padding:0;display:flex;flex-wrap:wrap;
gap:var(--s2) var(--s3);
font-size:.8125rem}
nav a{color:var(--muted)}
a:focus-visible,button:focus-visible{outline:3px solid var(--conditional);outline-offset:2px}
.eyebrow{font:.8125rem var(--data);letter-spacing:.06em;text-transform:uppercase;
color:var(--muted);margin:0}
.meta{font:.8125rem var(--data);color:var(--muted);margin:var(--s1) 0 var(--s4);
overflow-wrap:anywhere}
.copy{font:inherit;color:var(--ink);background:none;border:0;border-bottom:1px dotted var(--ink);
padding:0;cursor:pointer}
section{border-top:1px solid var(--rule);padding:var(--s3) 0 var(--s4);margin-top:var(--s3)}
h2{font:700 1.125rem var(--display);margin:0 0 var(--s3);letter-spacing:.01em}
h3{font:600 .9375rem var(--text);margin:var(--s4) 0 var(--s2)}
p,ul{margin:var(--s2) 0}
.muted{color:var(--muted)}
.num{font-family:var(--data);font-size:.875rem;overflow-wrap:anywhere}
.decision{font:700 2.75rem/1.05 var(--display);margin:0 0 var(--s3);letter-spacing:-.01em;
overflow-wrap:anywhere}
.release{color:var(--release)}.reject{color:var(--reject)}
.insufficient{color:var(--insufficient)}.conditional{color:var(--conditional)}
.reasons{padding-left:1.1rem}
.banner{border-left:4px solid var(--insufficient);background:var(--notrun);
padding:var(--s2) var(--s3);
font-weight:600;margin:0 0 var(--s3)}
.notrun{border:1px dashed var(--muted);background:var(--notrun);padding:var(--s2) var(--s3);
color:var(--muted)}
.notrun strong{color:var(--ink)}
dl.metrics{margin:0}
.row{display:grid;grid-template-columns:minmax(0,11rem) minmax(0,1fr);gap:var(--s2) var(--s3);
padding:var(--s3) 0;border-bottom:1px solid var(--rule)}
.row dt{font:600 .9375rem var(--data);overflow-wrap:anywhere}
.row dd{margin:0}
.ruler{display:block;width:100%;height:1.5rem;overflow:visible}
.ruler .track{stroke:var(--rule);stroke-width:1.5;vector-effect:non-scaling-stroke}
.ruler .ci{fill:var(--muted);opacity:.4;transform-origin:left;animation:grow 240ms ease-out}
.ruler .pt{stroke:var(--ink);stroke-width:3;vector-effect:non-scaling-stroke}
.ruler .appetite{stroke:var(--reject);stroke-width:2;vector-effect:non-scaling-stroke}
.uncovered{padding-left:1.1rem;font-family:var(--data);font-size:.875rem}
footer{border-top:1px solid var(--rule);padding-top:var(--s3);font-size:.8125rem}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){.ruler .ci{animation:none}}
@media (max-width:30rem){.row{grid-template-columns:minmax(0,1fr)}.decision{font-size:2rem}}
@media (min-width:68rem){
.page{display:grid;grid-template-columns:11rem minmax(0,46rem);gap:var(--s5)}
nav{position:sticky;top:var(--s4);align-self:start}
nav ol{display:block}nav li{margin-bottom:var(--s2)}}
"""

JS = """
document.querySelectorAll('.copy').forEach(function(b){b.addEventListener('click',function(){
var t=b.getAttribute('data-copy');if(navigator.clipboard){navigator.clipboard.writeText(t)}});});
"""
