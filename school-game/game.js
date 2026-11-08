'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = { data: null, missions: [], index: 0, score: 0, locked: false };
  const fmt = (v,d=0) => v!==null && v!==undefined && v!=='' && Number.isFinite(Number(v)) ? new Intl.NumberFormat('bn-BD',{maximumFractionDigits:d}).format(Number(v)) : 'উপলভ্য নয়';
  const pct = v => v!==null && v!==undefined && v!=='' && Number.isFinite(Number(v)) ? fmt(Number(v)*100)+'%' : 'উল্লেখ নেই';
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const show = (id,on=true) => $(id).classList.toggle('hidden',!on);
  const status = s => ({available:'উপলভ্য',partial:'আংশিক',stale:'পুরোনো cache',unavailable:'উপলভ্য নয়',not_configured:'সংযুক্ত নয়',pending:'অপেক্ষমাণ',retrying:'আবার চেষ্টা চলছে',error:'ত্রুটি'}[s]||s||'অজানা');
  const statusClass = s => ['available','partial','stale'].includes(s)?'good':['pending','retrying'].includes(s)?'pending':'limited';

  function makePayload(){
    const custom=$('location-mode').value==='custom';
    const lat=custom?Number($('latitude').value):24.75, lon=custom?Number($('longitude').value):90.41;
    const area=Number($('area').value), water=Number($('water-available').value), soil={};
    [['soil-ph','ph'],['soil-soc','soc_pct'],['soil-sand','sand_pct'],['soil-silt','silt_pct'],['soil-clay','clay_pct']].forEach(([id,k])=>{const v=$(id).value.trim();if(v!=='')soil[k]=Number(v);});
    const keys=['sand_pct','silt_pct','clay_pct'], count=keys.filter(k=>k in soil).length;
    if(!Number.isFinite(lat)||lat < -90||lat>90||!Number.isFinite(lon)||lon < -180||lon>180) throw Error('সঠিক Latitude ও Longitude দাও।');
    if(!Number.isFinite(area)||area<=0||area>10000) throw Error('জমির আয়তন ০-এর বেশি ও ১০,০০০ হেক্টরের মধ্যে হতে হবে।');
    if(!Number.isFinite(water)||water<0||water>5000) throw Error('মৌসুমে পাওয়া পানি ০–৫,০০০ mm-এর মধ্যে দাও।');
    if(count!==0&&count!==3) throw Error('Soil texture দিতে হলে Sand, Silt ও Clay—তিনটিই পূরণ করো।');
    if(count===3&&Math.abs(soil.sand_pct+soil.silt_pct+soil.clay_pct-100)>3) throw Error('Sand + Silt + Clay মোট ১০০%-এর কাছাকাছি হতে হবে।');
    if('ph' in soil&&(soil.ph<0||soil.ph>14)) throw Error('Soil pH ০–১৪-এর মধ্যে হতে হবে।');
    if('soc_pct' in soil&&(soil.soc_pct<0||soil.soc_pct>20)) throw Error('SOC ০–২০%-এর মধ্যে হতে হবে।');
    return {
      priority_choices:[$('priority').value],year:2026,n_weight_samples:60,n_uncertainty_samples:20,
      field:{lat:lat,lon:lon,area_ha:area,land_type:$('land-type').value,previous_crop:$('previous-crop').value,
        soil:soil,soil_data_source:Object.keys(soil).length?$('soil-source').value:'not-provided',
        farmer:{water_available_mm_season:water,irrigation_reliability:Number($('irrigation-reliability').value)}}
    };
  }

  function render(data){
    const q=data.data_quality||{}, snap=data.field_snapshot||{}, cov=q.remote_observation_coverage;
    const rows=[
      ['মডেলের পানি চাহিদা',snap.irrigation_mm,'mm / মৌসুম','Crop-rotation model estimate'],
      ['মডেল ফলন',snap.yield_kg_ha,'kg / হেক্টর','মাপা বাস্তব ফলন নয়'],
      ['মডেল নিট আয়',snap.net_return_bdt_ha,'BDT / হেক্টর','দাম ও খরচের অনুমানের ওপর নির্ভর'],
      ['Satellite evidence coverage',cov!==null&&cov!==undefined&&cov!==''&&Number.isFinite(Number(cov))?pct(cov):'উল্লেখ নেই','','Remote observation coverage']
    ];
    $('metric-grid').innerHTML=rows.map(r=>'<article class="metric-card"><span>'+esc(r[0])+'</span><strong>'+(typeof r[1]==='number'?fmt(r[1],1):esc(r[1]||'উল্লেখ নেই'))+'</strong><small>'+esc(r[2])+'</small><p>'+esc(r[3])+'</p></article>').join('');
    const level=q.level||'limited', note=level==='high'?'একাধিক উৎসের evidence পাওয়া গেছে; তবুও এটি জমির sensor বা soil test নয়।':level==='moderate'?'কিছু evidence পাওয়া গেছে, কিছু উৎস অনুপস্থিত বা অসম্পূর্ণ।':'Remote evidence সীমিত। কিছু ফল modeled বা synthetic input-এর ওপর নির্ভর করতে পারে।';
    $('quality-banner').className='quality-banner '+(level==='high'?'good':level==='moderate'?'pending':'limited');
    $('quality-banner').textContent=(q.label||'Evidence quality উল্লেখ নেই')+' — '+note;
    $('result-subtitle').textContent='Analysis ID: '+(data.run?.id||'এই সেশনের analysis')+' · Engine '+(data.run?.engine_version||'V3');

    const sources=data.evidence?.items||[];
    $('source-count').textContent=fmt(sources.length)+'টি source record';
    $('evidence-list').innerHTML=sources.map(s=>{
      const details=[s.source_type,s.retrieval_mode,s.data_end_date?'তথ্যের শেষ দিন: '+s.data_end_date:null,s.coverage].filter(Boolean).join(' · ');
      return '<article class="evidence-item"><div><strong>'+esc(s.name||'Evidence source')+'</strong><span class="status '+statusClass(s.status)+'">'+esc(status(s.status))+'</span></div><small>'+esc(details||'বিস্তারিত provenance নেই')+'</small>'+(s.fallback?'<p class="evidence-warning">Fallback: '+esc(s.fallback)+'</p>':'')+(s.quality_note?'<p>'+esc(s.quality_note)+'</p>':'')+'</article>';
    }).join('')||'<p class="empty-state">এই analysis-এ source record পাওয়া যায়নি।</p>';

    $('strategy-list').innerHTML=(data.strategies||[]).slice(0,3).map((s,i)=>{
      const m=s.metrics||{};
      return '<article class="strategy-item"><div class="strategy-top"><span>বিকল্প '+fmt(i+1)+'</span><strong>'+esc(s.label||'Crop strategy')+'</strong></div><p>'+esc((s.crop_ids||[]).join(' → ')||'Crop sequence')+'</p><div class="strategy-facts"><span>Risk-adjusted score<b>'+fmt(s.risk_adjusted_score,2)+'</b></span><span>পানি<b>'+fmt(m.water_mm,1)+' mm</b></span><span>মডেল নিট আয়<b>'+fmt(m.net_return_bdt_ha,0)+' টাকা/হে.</b></span></div><small>Top-1 probability: '+pct(s.top1_probability)+' · score range: '+((s.score_range||[]).map(x=>fmt(x,2)).join('–')||'উল্লেখ নেই')+'</small></article>';
    }).join('')||'<p class="empty-state">কোনো viable strategy পাওয়া যায়নি।</p>';
  }

  function missions(data){
    const q=data.data_quality||{}, top=data.strategies?.[0]||{}, m=top.metrics||{}, level=q.level||'limited';
    const quality=({high:'একাধিক উৎসের evidence',moderate:'মিশ্র evidence',limited:'সীমিত evidence'})[level]||'সীমিত evidence';
    return [
      {title:'মিশন ১ · Evidence quality',question:'এই analysis-এ তথ্যের মান কীভাবে দেখানো হয়েছে?',correct:quality,options:[quality,'সব তথ্য ১০০% নিশ্চিত','সম্পূর্ণ মাঠ-পরিমাপ'],why:'Data quality হলো '+quality+'। এটি মাঠের soil test বা sensor measurement নয়।'},
      {title:'মিশন ২ · Missing data',question:'কোনো NASA source unavailable হলে সেটিকে কীভাবে ধরবে?',correct:'অনুপস্থিত তথ্য; শূন্য নয়',options:['অনুপস্থিত তথ্য; শূন্য নয়','বৃষ্টিপাত ০ mm','নিজে থেকে অনুমান করে observed বলব'],why:'Missing data মানে শূন্য নয়। unavailable, partial ও modeled মান আলাদা রাখতে হয়।'},
      {title:'মিশন ৩ · পানি ব্যবহার',question:'শীর্ষ strategy-র modeled irrigation demand কত?',correct:fmt(m.water_mm,1)+' mm / মৌসুম',options:[fmt(m.water_mm,1)+' mm / মৌসুম','সব জমিতে ০ mm','এই তথ্যের কোনো একক নেই'],why:'এটি crop-rotation model estimate; সেন্সরে মাপা পানি নয়।'},
      {title:'মিশন ৪ · Crop strategy',question:'শীর্ষে থাকা পরিকল্পনাটি কি নিশ্চিত ফলন বা লাভের প্রতিশ্রুতি?',correct:'না, এটি মডেলের estimate',options:['হ্যাঁ, নিশ্চিত লাভ','না, এটি মডেলের estimate','এটি সরাসরি NASA satellite measurement'],why:'শীর্ষ strategy: '+(top.label||'উল্লেখ নেই')+'। ranking, yield ও net return modeled; বাস্তব ফল বদলাতে পারে।'},
      {title:'মিশন ৫ · নিরাপদ পদক্ষেপ',question:'বাস্তব জমিতে সিদ্ধান্ত নেওয়ার আগে কী করবে?',correct:'Soil test ও স্থানীয় কৃষি পরামর্শ যাচাই',options:['মডেলকে চূড়ান্ত নির্দেশ ধরব','Soil test ও স্থানীয় কৃষি পরামর্শ যাচাই','অনুপস্থিত satellite data-কে শূন্য ধরব'],why:'FieldShift সিদ্ধান্ত বোঝাতে সাহায্য করে; স্থানীয় কৃষি বিশেষজ্ঞ, soil test ও মাঠের বাস্তবতার বিকল্প নয়।'}
    ];
  }
  function renderMission(){
    const m=state.missions[state.index];state.locked=false;
    $('mission-number').textContent='মিশন '+fmt(state.index+1)+' / ৫';$('score').textContent=fmt(state.score);
    $('progress-fill').style.width=(state.index/5*100)+'%';
    $('mission-card').innerHTML='<p class="mission-label">'+esc(m.title)+'</p><h3>'+esc(m.question)+'</h3><div class="mission-options">'+m.options.map((v,i)=>'<button type="button" class="mission-option" data-choice="'+i+'">'+fmt(i+1)+'. '+esc(v)+'</button>').join('')+'</div>';
    $('mission-feedback').textContent='';$('mission-feedback').className='mission-feedback';show('next-mission',false);
    $('mission-card').querySelectorAll('[data-choice]').forEach(b=>b.addEventListener('click',()=>answer(Number(b.dataset.choice))));
  }
  function answer(i){
    if(state.locked)return;state.locked=true;
    const m=state.missions[state.index],picked=m.options[i],right=picked===m.correct;if(right)state.score+=10;
    $('mission-card').querySelectorAll('button').forEach(b=>{const c=m.options[Number(b.dataset.choice)];b.disabled=true;if(c===m.correct)b.classList.add('correct');else if(c===picked)b.classList.add('incorrect');});
    $('mission-feedback').className='mission-feedback '+(right?'success':'learning');
    $('mission-feedback').textContent=(right?'সঠিক উত্তর! +১০ পয়েন্ট। ':'শেখার সুযোগ। ')+m.why;
    $('score').textContent=fmt(state.score);$('next-mission').textContent=state.index===4?'ফলাফল দেখো':'পরের মিশন →';show('next-mission');
  }
  function finish(){
    show('mission-panel',false);show('finish',true);$('progress-fill').style.width='100%';
    const d=state.data,top=d.strategies?.[0]||{},q=d.data_quality||{},f=d.field||{};
    $('final-score').textContent=fmt(state.score);
    $('finish-summary').textContent='তুমি পাঁচটি মিশন শেষ করেছ এবং '+fmt(state.score)+' পয়েন্ট পেয়েছ। Evidence, model estimate ও মাঠের বাস্তবতা এক জিনিস নয়—এটাই সবচেয়ে গুরুত্বপূর্ণ শিক্ষা।';
    $('family-report').textContent=[
      'KRISHINEXUS · FIELD SHIFT LEARNING NOTE',
      'স্থানাঙ্ক: '+fmt(f.location?.lat,4)+', '+fmt(f.location?.lon,4)+' · জমি: '+fmt(f.area_ha,2)+' হেক্টর',
      'Evidence quality: '+(q.label||'উল্লেখ নেই')+' · Run ID: '+(d.run?.id||'উল্লেখ নেই'),
      'শীর্ষ মডেল strategy: '+(top.label||'উল্লেখ নেই'),
      'মডেল পানি চাহিদা: '+fmt(top.metrics?.water_mm,1)+' mm/season',
      'মডেল ফলন: '+fmt(top.metrics?.yield_kg_ha,1)+' kg/ha',
      'মডেল নিট আয়: '+fmt(top.metrics?.net_return_bdt_ha,0)+' BDT/ha','',
      'পরিবারের সাথে আলোচনা:','১) জমির soil test কবে করা হয়েছে?','২) মৌসুমে বাস্তবে কত পানি পাওয়া যায়?','৩) স্থানীয় কৃষি কর্মকর্তা এই crop plan সমর্থন করেন কি?','',
      'সতর্কতা: এগুলো model estimates, নিশ্চিত ফলন/লাভ নয়। NASA POWER gridded point data জমির sensor নয়। Missing data শূন্য নয়। স্থানীয় যাচাই আবশ্যক।'
    ].join('\n');
  }

  $('analysis-form').addEventListener('submit',async e=>{
    e.preventDefault();$('form-error').textContent='';
    let payload;try{payload=makePayload();}catch(err){$('form-error').textContent=err.message;return;}
    $('run-analysis').disabled=true;$('run-analysis').textContent='Analysis চলছে…';
    show('analysis-state');show('results',false);show('finish',false);
    $('loading-title').textContent='FieldShift V3 analysis চলছে';
    $('loading-copy').textContent='ইনপুট যাচাই, NASA POWER request ও crop-rotation calculation হচ্ছে। কোনো satellite উৎস অনুপলভ্য হলে তা আলাদা দেখানো হবে।';
    const ctl=new AbortController(),timer=setTimeout(()=>ctl.abort(),240000);
    try{
      const res=await fetch('/api/analysis/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:ctl.signal});
      const body=await res.json().catch(()=>({}));
      if(!res.ok)throw Error(body.detail||('Analysis failed (HTTP '+res.status+')'));
      if(!body.strategies||!body.evidence||!body.run)throw Error('API response structure incomplete; result was not displayed.');
      state.data=body;state.missions=missions(body);state.index=0;state.score=0;render(body);
      show('analysis-state',false);show('results');renderMission();$('results').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(err){$('form-error').textContent=err.name==='AbortError'?'Analysis ৪ মিনিটের মধ্যে শেষ হয়নি। আবার চেষ্টা করো।':err.message;show('analysis-state',false);}
    finally{clearTimeout(timer);$('run-analysis').disabled=false;$('run-analysis').innerHTML='<span>বাস্তব analysis চালাও</span><span aria-hidden="true">→</span>';}
  });
  $('location-mode').addEventListener('change',()=>{const custom=$('location-mode').value==='custom';document.querySelectorAll('.custom-field').forEach(el=>el.classList.toggle('hidden',!custom));if(custom)$('latitude').focus();});
  $('rerun').addEventListener('click',()=>$('setup-title').scrollIntoView({behavior:'smooth',block:'start'}));
  $('next-mission').addEventListener('click',()=>{state.index++;if(state.index>=5)finish();else renderMission();});
  $('print-report').addEventListener('click',()=>window.print());
  $('play-again').addEventListener('click',()=>{show('finish',false);show('results',false);$('analysis-form').reset();$('location-mode').dispatchEvent(new Event('change'));$('setup-title').scrollIntoView({behavior:'smooth'});});
})();