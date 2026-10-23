
const sections=[...document.querySelectorAll('main>section')];
const links=[...document.querySelectorAll('.navitem')];
let current=0;
sections.forEach((section,index)=>{
 const pager=document.createElement('div');pager.className='pager';
 const previous=document.createElement('button');previous.type='button';previous.textContent='上一环节';previous.disabled=index===0;previous.addEventListener('click',()=>show(index-1,true));
 const count=document.createElement('span');count.textContent=(index+1)+' / '+sections.length;count.setAttribute('aria-label','环节进度');
 const next=document.createElement('button');next.type='button';next.textContent='下一环节';next.disabled=index===sections.length-1;next.addEventListener('click',()=>show(index+1,true));
 pager.append(previous,count,next);section.append(pager);
});
function show(index,focus){
 current=Math.max(0,Math.min(sections.length-1,index));
 sections.forEach((section,i)=>section.hidden=i!==current);
 links.forEach((link,i)=>{link.classList.toggle('active',i===current);if(i===current)link.setAttribute('aria-current','step');else link.removeAttribute('aria-current');});
 if(location.hash!=='#'+sections[current].id)history.replaceState(null,'','#'+sections[current].id);
 if(focus){const heading=sections[current].querySelector('h2');heading.tabIndex=-1;heading.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
}
links.forEach((link,index)=>link.addEventListener('click',event=>{event.preventDefault();show(index,true);}));
window.addEventListener('hashchange',()=>{const i=sections.findIndex(s=>'#'+s.id===location.hash);if(i>=0)show(i,false);});
const initial=sections.findIndex(s=>'#'+s.id===location.hash);show(initial<0?0:initial,false);
