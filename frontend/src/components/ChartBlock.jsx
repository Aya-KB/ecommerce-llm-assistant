// components/ChartBlock.jsx
// Affiche UN SEUL graphe selon chart.type reçu du backend.
// Pas de sélecteur — le type est décidé par la question de l'utilisateur.

import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";

const PALETTE = ["#111110","#3d3d3b","#6b6b68","#16a34a","#dc2626","#2563eb","#f59e0b","#9ca3af"];

// ── Tooltip ────────────────────────────────────────────
function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background:"#fff", border:"1px solid #e8e5e0",
      borderRadius:8, padding:"8px 13px", fontSize:12,
      boxShadow:"0 4px 16px rgba(0,0,0,0.08)",
    }}>
      {label && <p style={{color:"#6f6e69",marginBottom:4,fontWeight:600}}>{label}</p>}
      {payload.map((p,i) => (
        <p key={i} style={{color:p.color||"#111110",margin:"2px 0",display:"flex",justifyContent:"space-between",gap:16}}>
          <span style={{color:"#a8a39a"}}>{p.name}</span>
          <strong>{fmt(p.value)}</strong>
        </p>
      ))}
    </div>
  );
}

// ── Label Pie ──────────────────────────────────────────
function PieLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.05) return null;
  const R = Math.PI / 180;
  const r = innerRadius + (outerRadius - innerRadius) * 0.55;
  return (
    <text x={cx + r*Math.cos(-midAngle*R)} y={cy + r*Math.sin(-midAngle*R)}
      fill="#fff" textAnchor="middle" dominantBaseline="central"
      fontSize={11} fontWeight={700}>
      {(percent*100).toFixed(0)}%
    </text>
  );
}

// ── Formatage ──────────────────────────────────────────
function fmt(v) {
  if (v == null) return "—";
  if (typeof v !== "number") return String(v);
  if (Math.abs(v) >= 1_000_000) return `${(v/1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000)     return `${(v/1_000).toFixed(1)}k`;
  return v.toLocaleString("fr-FR", { maximumFractionDigits:2 });
}
function fmtAxis(v) {
  if (typeof v === "string" && v.length > 13) return v.slice(0,12)+"…";
  return fmt(v);
}

const AXIS  = { tick:{fill:"#a8a39a",fontSize:11}, axisLine:false, tickLine:false };
const GRID  = { strokeDasharray:"3 3", stroke:"#f0ede8", vertical:false };

// ── Un seul graphe selon type ──────────────────────────
function renderChart(type, data, xKey, yKeys, colors) {
  const c0 = colors[0] || PALETTE[0];

  if (type === "line") return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{top:4,right:16,left:0,bottom:36}}>
        <CartesianGrid {...GRID}/>
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={fmtAxis} height={44}/>
        <YAxis {...AXIS} tickFormatter={fmtAxis} width={50}/>
        <Tooltip content={<Tip/>}/>
        {yKeys.length>1 && <Legend wrapperStyle={{fontSize:11,color:"#a8a39a"}}/>}
        {yKeys.map((k,i) => (
          <Line key={k} type="monotone" dataKey={k}
            stroke={colors[i]||PALETTE[i%PALETTE.length]}
            strokeWidth={2.5} dot={false} activeDot={{r:5,strokeWidth:0}}/>
        ))}
      </LineChart>
    </ResponsiveContainer>
  );

  if (type === "pie") return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie data={data} dataKey={yKeys[0]} nameKey={xKey}
          cx="50%" cy="50%" innerRadius={60} outerRadius={110}
          paddingAngle={2} labelLine={false} label={PieLabel}>
          {data.map((_,i) => <Cell key={i} fill={colors[i%colors.length]||PALETTE[i%PALETTE.length]}/>)}
        </Pie>
        <Tooltip formatter={(v,n)=>[fmt(v),n]}
          contentStyle={{background:"#fff",border:"1px solid #e8e5e0",borderRadius:8,fontSize:12}}/>
        <Legend formatter={v=><span style={{fontSize:11,color:"#a8a39a"}}>{v}</span>}/>
      </PieChart>
    </ResponsiveContainer>
  );

  if (type === "scatter") return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{top:4,right:16,left:0,bottom:36}}>
        <CartesianGrid {...GRID}/>
        <XAxis dataKey={xKey} name={xKey} {...AXIS} type="number" tickFormatter={fmtAxis} width={50}/>
        <YAxis dataKey={yKeys[0]} name={yKeys[0]} {...AXIS} tickFormatter={fmtAxis} width={50}/>
        <Tooltip cursor={{strokeDasharray:"3 3"}} content={<Tip/>}/>
        <Scatter data={data} fill={c0} fillOpacity={0.7}/>
      </ScatterChart>
    </ResponsiveContainer>
  );

  if (type === "area") return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{top:4,right:16,left:0,bottom:36}}>
        <defs>
          {yKeys.map((k,i) => (
            <linearGradient key={k} id={`ag${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={colors[i]||PALETTE[i%PALETTE.length]} stopOpacity={0.2}/>
              <stop offset="100%" stopColor={colors[i]||PALETTE[i%PALETTE.length]} stopOpacity={0}/>
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid {...GRID}/>
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={fmtAxis} height={44}/>
        <YAxis {...AXIS} tickFormatter={fmtAxis} width={50}/>
        <Tooltip content={<Tip/>}/>
        {yKeys.map((k,i) => (
          <Area key={k} type="monotone" dataKey={k}
            stroke={colors[i]||PALETTE[i%PALETTE.length]}
            strokeWidth={2.5} fill={`url(#ag${i})`}/>
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );

  // bar (défaut)
  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{top:4,right:16,left:0,bottom:56}}>
        <CartesianGrid {...GRID}/>
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={fmtAxis}
          angle={-30} textAnchor="end" interval={0} height={64}/>
        <YAxis {...AXIS} tickFormatter={fmtAxis} width={50}/>
        <Tooltip content={<Tip/>} cursor={{fill:"rgba(17,17,16,0.04)"}}/>
        {yKeys.length>1 && <Legend wrapperStyle={{fontSize:11,color:"#a8a39a"}}/>}
        {yKeys.map((k,i) => (
          <Bar key={k} dataKey={k}
            fill={colors[i]||PALETTE[i%PALETTE.length]}
            radius={[4,4,0,0]} maxBarSize={44}/>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Composant principal ────────────────────────────────
export default function ChartBlock({ chart }) {
  if (!chart?.data?.length) return null;

  const { type, title, data, x_key, y_keys, colors } = chart;

  return (
    <div style={{
      background:"#fff", border:"1px solid #e8e5e0",
      borderRadius:12, padding:"14px 14px 8px", marginTop:8,
    }}>
      {/* Titre + badge type */}
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12}}>
        {title && (
          <span style={{fontSize:12,fontWeight:600,color:"#6f6e69",flex:1}}>
            {title}
          </span>
        )}
        <span style={{
          fontSize:10, fontWeight:600, color:"#a8a39a",
          background:"#f5f4f1", borderRadius:4, padding:"2px 7px",
          textTransform:"uppercase", letterSpacing:".04em",
        }}>
          {type}
        </span>
      </div>

      {/* Le graphe unique */}
      {renderChart(type, data, x_key, y_keys, colors || PALETTE)}

      {/* Footer */}
      <p style={{fontSize:10,color:"#c0bbb4",textAlign:"right",marginTop:4}}>
        {data.length} résultats
      </p>
    </div>
  );
}