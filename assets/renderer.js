/* Local Markdown + MathJax renderer. Math is protected before Markdown parsing. */
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const content=document.getElementById('content');
let queue=Promise.resolve(), latest=0;
window.previewState={ready:false,errors:[],mathCount:0};
function prepareMarkdown(input){
 let text=input.replace(/^\uFEFF?---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/,'');
 const math=[];
 const nonce='MW'+Math.random().toString(36).slice(2)+'TOKEN';
 function protect(html,block){const token=nonce+math.length+'END';math.push({token,html});return block?'\n\n'+token+'\n\n':token;}
 // Remove one quote level before protecting math. Otherwise a quoted $$ block
 // sends its Markdown > prefixes to MathJax as part of the TeX expression.
 const lines=text.split(/\r?\n/),out=[];
 let fence=null;
 for(let i=0;i<lines.length;i++){
  const marker=lines[i].match(/^\s*(`{3,}|~{3,})/);
  if(marker){const ch=marker[1][0];fence=fence===ch?null:(fence||ch);}
  if(!fence&&/^> ?/.test(lines[i])){
   const quoted=[];
   while(i<lines.length&&/^> ?/.test(lines[i]))quoted.push(lines[i++].replace(/^> ?/,''));
   i--;
   const header=quoted[0].match(/^\[!([\w-]+)\]([+-]?)(?:\s+(.*))?$/);
   if(header){
    const type=header[1].toLowerCase(),fold=header[2];
    const names={abstract:'定义',note:'定理',tip:'证明',example:'例题',warning:'条件与限制',info:'直观解释',quote:'保留记录'};
    const title=esc(header[3]||names[type]||header[1]);
    const body=prepareMarkdown(quoted.slice(1).join('\n'));
    const heading='<span class="callout-mark" aria-hidden="true">'+({abstract:'≔',note:'∎',tip:'✓',example:'◇',warning:'!',info:'i',quote:'↳'}[type]||'◇')+'</span>'+title;
    const attrs=' class="callout" data-callout="'+esc(type)+'"';
    const html=fold?'<details'+attrs+(fold==='+'?' open':'')+'><summary>'+heading+'</summary><div class="callout-content">'+body+'</div></details>':'<section'+attrs+'><div class="callout-title">'+heading+'</div><div class="callout-content">'+body+'</div></section>';
    out.push(protect(html,true));
   }else out.push(protect('<blockquote>'+prepareMarkdown(quoted.join('\n'))+'</blockquote>',true));
  }else out.push(lines[i]);
 }
 text=out.join('\n');
 const pattern=/(```[\s\S]*?```|~~~[\s\S]*?~~~|`+[^`]*`+|^(?: {4}|\t)[^\n]*(?:\n(?: {4}|\t)[^\n]*)*)|\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|(?<![\\$])\$(?!\$)([^\n$]+?)(?<!\\)\$(?!\$)|\\begin\{(align\*?|equation\*?|gather\*?)\}([\s\S]*?)\\end\{\6\}/gm;
 text=text.replace(pattern,(match,code,display,bracket,inline,dollar,env)=>{
   if(code)return protect(/^(?:```|~~~| {4}|\t)/.test(code)?marked.parse(code):marked.parseInline(code),false);
   const block=display!==undefined||bracket!==undefined||env!==undefined;
   const tex=display??bracket??inline??dollar??match;
   return protect(block?'<div class="math-block">\\['+esc(tex)+'\\]</div>':'<span class="math-inline">\\('+esc(tex)+'\\)</span>',block);
 });
 text=text.replace(/\[\[([^\]\n]+)\]\]/g,(_,v)=>{const parts=v.split('|');const target=parts[0];const label=parts[1]||target;return '<a class="wiki" href="mathnote:'+encodeURIComponent(target)+'">'+esc(label)+'</a>';});
 let html=marked.parse(text,{gfm:true,breaks:false});
 for(const m of math)html=html.replace('<p>'+m.token+'</p>',m.html).replaceAll(m.token,m.html);
 return DOMPurify.sanitize(html,{ALLOWED_URI_REGEXP:/^(?:(?:https?|mailto|mathnote):|#)/i,FORBID_TAGS:['style','iframe','object','embed','script'],FORBID_ATTR:['style']});
}
window.renderNote=function(payload){
 const revision=++latest;
 window.previewState={ready:false,errors:[],mathCount:0};
 queue=queue.catch(()=>{}).then(async()=>{
   if(revision!==latest)return;
   try{
    await MathJax.startup.promise;
    if(revision!==latest)return;
    MathJax.typesetClear([content]);
    MathJax.texReset();
    document.body.classList.toggle('dark',!!payload.dark);
    const chips=(payload.tags||[]).slice(0,7).map(t=>'<span class="chip">'+esc(t)+'</span>').join('');
    content.innerHTML='<div class="badge">MATHEMATICS · CONNECTED NOTES</div><div class="properties">'+chips+'</div>'+prepareMarkdown(payload.markdown);
    await MathJax.typesetPromise([content]);
    const errors=[...content.querySelectorAll('mjx-merror')].map(el=>el.getAttribute('data-mjx-error')||el.textContent);
    window.previewState={ready:true,errors,mathCount:content.querySelectorAll('mjx-container').length};
   }catch(err){window.previewState={ready:true,errors:[String(err)],mathCount:0};content.insertAdjacentHTML('afterbegin','<div class="error">公式预览出现问题：'+esc(err)+'</div>');}
 });return revision;
};
window.renderGraph=function(payload){
 ++latest;
 const nodes=payload.nodes||[], edges=payload.edges||[];
 const columns=nodes.length>3?3:Math.max(nodes.length,1), width=720, rows=Math.ceil(nodes.length/columns), height=Math.max(300,rows*145+70);
 const positions=new Map(nodes.map((n,i)=>[n.title,{x:(i%columns+.5)*width/columns,y:70+Math.floor(i/columns)*145}]));
 let svg='<svg class="graph" viewBox="0 0 '+width+' '+height+'"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#b4aacb"/></marker></defs>';
 for(const edge of edges){const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)continue;const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy)||1;const sx=a.x+dx/len*55,sy=a.y+dy/len*29,tx=b.x-dx/len*60,ty=b.y-dy/len*32;svg+='<path d="M'+sx+' '+sy+' Q'+((sx+tx)/2)+' '+((sy+ty)/2-24)+' '+tx+' '+ty+'" stroke="#b4aacb" fill="none" stroke-width="1.8" marker-end="url(#arrow)"/><text class="edge-label" x="'+((sx+tx)/2)+'" y="'+((sy+ty)/2-18)+'" text-anchor="middle">'+esc(edge.relation)+'</text>';}
 for(const node of nodes){const p=positions.get(node.title);svg+='<a class="node" href="mathnote:'+encodeURIComponent(node.title)+'"><rect x="'+(p.x-91)+'" y="'+(p.y-30)+'" width="182" height="60" rx="13"/><text x="'+p.x+'" y="'+(p.y-1)+'" text-anchor="middle">'+esc(node.title.length>12?node.title.slice(0,12)+'…':node.title)+'</text><text x="'+p.x+'" y="'+(p.y+18)+'" text-anchor="middle" style="font-size:10px;fill:#9890ae">'+esc(node.category)+'</text></a>';}
 svg+='</svg>';
 const list=edges.map(e=>'<div class="relation-item"><a href="mathnote:'+encodeURIComponent(e.source)+'">'+esc(e.source)+'</a> <b>'+esc(e.relation)+'</b> <a href="mathnote:'+encodeURIComponent(e.target)+'">'+esc(e.target)+'</a><div class="reason">'+esc(e.reason||'')+'</div></div>').join('');
 content.innerHTML='<div class="badge">KNOWLEDGE CONNECTIONS</div><h1>把知识点，织成网</h1><p style="color:#8891a4;font-size:13px">点击节点阅读笔记。箭头表示关系方向，互链会一并保存到 Obsidian。</p>'+svg+'<div class="relations">'+(list||'对话没有明确提供联系，因此保持概念独立。')+'</div>';
 window.previewState={ready:true,errors:[],mathCount:0};
};

