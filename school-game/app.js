(() => {
"use strict";
const $=id=>document.getElementById(id), regions={mymensingh:[24.75,90.41],dhaka:[23.81,90.41],rajshahi:[24.37,88.60],rangpur:[25.75,89.25],khulna:[22.85,89.54],barishal:[22.70,90.35],sylhet:[24.89,91.87],chattogram:[22.36,91.78],rangamati:[22.65,92.18]};
let result=null,questions=[],qi=0,score=0;
const num=id=>Number($(id).value),esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const present=v=>v!==null&&v!==undefined&&v!==""&&Number.isFinite(Number(v));
const show=(id,on=true)=>$(id).classList.toggle("hidden",!on),fmt=(v,d=0)=>present(v)?Number(v).toLocaleString("en-US",{maximumFractionDigits:d}):"উল্লেখ নেই",pct=v=>present(v)?fmt(Number(v)*100,1)+"%":"উল্লেখ নেই";
const labels={available:"পাওয়া গেছে",partial:"আংশিক",stale:"পুরোনো cache",pending:"অপেক্ষমাণ",retrying:"আবার চেষ্টা হচ্ছে",unavailable:"পাওয়া যায়নি",not_archived:"archive নেই",not_downloaded:"ডাউনলোড হয়নি"};
$("region").addEventListener("change",()=>{const k=$("region").value,custom=k==="custom";show("lat-field",custom);show("lon-field",custom);if(!custom){$("lat").value=regions[k][0];$("lon").value=regions[k][1];}});
function payload(){
const k=$("region").value,lat=k==="custom"?num("lat"):regions[k][0],lon=k==="custom"?num("lon"):regions[k][1],area=num("area"),water=num("water-available");
if(!Number.isFinite(lat)||lat< -90||lat>90||!Number.isFinite(lon)||lon< -180||lon>180)throw Error("Latitude ও longitude সঠিকভাবে দাও।");
if(!Number.isFinite(area)||area<=0||area>10000)throw Error("ক্ষেতের আয়তন ০-এর বেশি ও ১০,০০০ হেক্টরের মধ্যে হতে হবে।");
if(!Number.isFinite(water)||water<0||water>5000)throw Error("মৌসুমে পানির পরিমাণ ০–৫,০০০ mm-এর মধ্যে দাও।");
const soil={};for(const [key,id] of [["ph","soil-ph"],["soc_pct","soil-soc"],["sand_pct","soil-sand"],["silt_pct","soil-silt"],["clay_pct","soil-clay"]]){const v=$(id).value.trim();if(v!=="")soil[key]=Number(v);}
if(["sand_pct","silt_pct","clay_pct"].some(x=>x in soil)){if(!["sand_pct","silt_pct","clay_pct"].every(x=>Number.isFinite(soil[x])))throw Error("Texture দিতে Sand, Silt ও Clay—তিনটিই পূরণ করো।");if(Math.abs(soil.sand_pct+soil.silt_pct+soil.clay_pct-100)>2)throw Error("Sand + Silt + Clay যোগফল 100% (±2%) হতে হবে।");}
return {field:{lat,lon,area_ha:area,land_type:$("land-type").value,previous_crop:$("previous-crop").value,soil,soil_data_source:Object.keys(soil).length?"farmer-reported":"regional-defaults",farmer:{water_available_mm_season:water,irrigation_reliability:num("irrigation-reliability"),budget_bdt_ha:100000,labour_available_person_days_ha:120}},priority_choices:[$("priority").value],year:new Date().getFullYear(),n_weight_samples:80,n_uncertainty_samples:24};
}
function render(data){
const items=data.evidence?.items||[],quality=data.data_quality||{},qtext={high:"Multi-source evidence পাওয়া গেছে",moderate:"Evidence coverage মিশ্র",limited:"Remote evidence সীমিত; ফল বেশি নির্ভর করছে model/default inputs-এর ওপর"};
const coverage=present(quality.coverage_fraction)?fmt(Number(quality.coverage_fraction)*100,1)+"%":"উল্লেখ নেই";
$("quality").innerHTML="<b>"+esc(qtext[quality.level]||"Evidence status")+"</b><span>"+esc(quality.label||quality.level||"Unknown")+" · coverage "+coverage+"</span>";
$("evidence").innerHTML=items.length?items.map(x=>"<div class='source'><div><b>"+esc(x.name)+"</b><small>"+esc(x.source_type||"source")+" · "+esc(x.retrieval_mode||"status not specified")+"</small></div><span class='status "+esc(x.status)+"'>"+esc(labels[x.status]||x.status||"অজানা")+"</span><p>"+esc(x.quality_note||x.error||x.fallback||x.setup_hint||"Source status recorded in analysis provenance.")+"</p></div>").join(""):"<p>এই run-এ source-level evidence record পাওয়া যায়নি।</p>";
$("strategies").innerHTML=data.strategies.slice(0,4).map((s,i)=>{const m=s.metrics||{},range=s.score_range||[];return "<article class='strategy'><span class='rank'>#"+(i+1)+"</span><div><b>"+esc(s.label||s.id)+"</b><small>Modelled score range: "+fmt(range[0],2)+"–"+fmt(range[1],2)+" · top-1 probability "+pct(s.top1_probability)+"</small><p>"+(s.crop_ids||[]).map(esc).join(" → ")+"</p><div class='strategy-metrics'><span>Water "+fmt(m.water_mm)+" mm</span><span>Yield "+fmt(m.yield_kg_ha)+" kg/ha</span><span>Net return ৳"+fmt(m.net_return_bdt_ha)+"</span></div></div></article>";}).join("");
$("source-count").textContent=items.length+" source";
$("result-summary").textContent=(data.field?.location?.label||"Selected field")+" · "+(data.field?.area_ha??"—")+" ha · "+(data.run?.mode||"analysis");
}
function quiz(data){
const items=data.evidence?.items||[],usable=items.filter(x=>["available","partial","stale"].includes(x.status)),top=data.strategies[0],level=data.data_quality?.level||"unknown",quality={high:"উচ্চ",moderate:"মাঝারি",limited:"সীমিত",unknown:"অজানা"}[level]||level;
questions=[
{q:"এই analysis-এ source record অনুযায়ী usable evidence কয়টি?",choices:[String(usable.length),String(usable.length+1),String(Math.max(0,usable.length-1))],a:String(usable.length),why:"Available, partial এবং stale record গণনা করা হয়েছে; stale মানে fresh নয়।"},
{q:"এই run-এ FieldShift কোন strategy-কে প্রথমে রেখেছে?",choices:[top.label,data.strategies[1]?.label||"দ্বিতীয় strategy নেই","কোনো crop model চালানো হয়নি"],a:top.label,why:"এটি এই run-এর model ranking; বাস্তব harvest measurement নয়।"},
{q:"তোমার evidence quality label কী?",choices:[quality,"নিশ্চিতভাবে validated","সবসময় 100%"],a:quality,why:"Evidence quality provenance ও coverage-এর সারাংশ; field-level validation নয়।"}];
qi=0;score=0;question();
}
function question(){
const q=questions[qi];$("score").textContent=score+" / "+questions.length;$("progress-fill").style.width=(qi/questions.length*100)+"%";
$("question").innerHTML="<p class='question-count'>প্রশ্ন "+(qi+1)+" / "+questions.length+"</p><h3>"+esc(q.q)+"</h3><div class='choices'>"+q.choices.map((x,i)=>"<button class='choice' data-i='"+i+"'>"+esc(x)+"</button>").join("")+"</div>";
$("feedback").textContent="";show("next",false);
document.querySelectorAll(".choice").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".choice").forEach(x=>x.disabled=true);const ok=q.choices[Number(b.dataset.i)]===q.a;if(ok)score++;b.classList.add(ok?"correct":"wrong");document.querySelectorAll(".choice").forEach(x=>{if(x.textContent===q.a)x.classList.add("correct");});$("score").textContent=score+" / "+questions.length;$("feedback").textContent=(ok?"ঠিক উত্তর। ":"আবার ভাবো। ")+q.why;$("next").textContent=qi===questions.length-1?"ফলাফল দেখো":"পরের প্রশ্ন →";show("next",true);}));
}
function finish(){
$("progress-fill").style.width="100%";$("final-score").textContent=score+" / "+questions.length;
const top=result.strategies[0];$("finish-note").textContent="তোমার field analysis-এ "+top.label+" শীর্ষে ছিল। Evidence quality: "+(result.data_quality?.level||"unknown")+". Local validation ও farmer judgement ছাড়া model output চূড়ান্ত সিদ্ধান্ত নয়.";
show("finish",true);$("finish").scrollIntoView({behavior:"smooth",block:"start"});
}
async function run(){
$("form-error").textContent="";let body;try{body=payload();}catch(e){$("form-error").textContent=e.message;return;}
$("run-analysis").disabled=true;$("run-analysis").textContent="Analysis চলছে…";show("loading",true);show("results",false);show("challenge",false);show("finish",false);
try{const r=await fetch("/api/analysis/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),data=await r.json();if(!r.ok)throw Error(data.detail||"Analysis request failed");if(!Array.isArray(data.strategies)||!data.strategies.length)throw Error("API response-এ viable strategy পাওয়া যায়নি।");result=data;render(data);quiz(data);show("loading",false);show("results",true);show("challenge",true);$("results").scrollIntoView({behavior:"smooth",block:"start"});}
catch(e){show("loading",false);$("form-error").textContent="Analysis সম্পন্ন হয়নি: "+e.message+". API ও upstream source status পরীক্ষা করো।";}
finally{$("run-analysis").disabled=false;$("run-analysis").textContent="FieldShift analysis চালাও ↗";}
}
$("analysis-form").addEventListener("submit",e=>{e.preventDefault();run();});$("rerun").addEventListener("click",run);
$("next").addEventListener("click",()=>{qi++;if(qi<questions.length)question();else finish();});
$("print").addEventListener("click",()=>window.print());$("again").addEventListener("click",()=>{show("finish",false);show("challenge",false);show("results",false);$("analysis-form").scrollIntoView({behavior:"smooth"});});
})();