/* Tour guiado (base: tour da Triagem IPH, adaptado para a Agenda Diana em 25/11/2026).
   Passos por tela em <script type="application/json" id="tour-passos">.
   NUNCA abre sozinho: só pelo botão .tour-btn. Depois de aberto, a jornada segue nas próximas telas
   (sessionStorage) até a pessoa concluir ou sair. */
var Tour=(function(){
  var passos=[],i=0,luz,card,alvo=null,chave="tourJornada";
  function ls(op,k,v){try{return op==="get"?localStorage.getItem(k):localStorage.setItem(k,v);}catch(e){return null;}}
  function ss(op,k,v){try{return op==="get"?sessionStorage.getItem(k):op==="set"?sessionStorage.setItem(k,v):sessionStorage.removeItem(k);}catch(e){return null;}}
  function ler(){var el=document.getElementById("tour-passos");if(!el)return[];try{return JSON.parse(el.textContent).filter(function(p){return !p.alvo||document.querySelector(p.alvo);});}catch(e){return[];}}
  function fechar(fim){if(luz)luz.remove();if(card)card.remove();luz=card=null;window.removeEventListener("resize",posicionar);window.removeEventListener("scroll",posicionar,true);if(fim){ss("del",chave);ls("set","tourFeito","1");}}
  function posicionar(){
    if(!card)return;var r=alvo?alvo.getBoundingClientRect():null,m=8;
    if(r){luz.classList.remove("sem-alvo");luz.style.left=(r.left-m)+"px";luz.style.top=(r.top-m)+"px";luz.style.width=(r.width+2*m)+"px";luz.style.height=(r.height+2*m)+"px";}
    else{luz.classList.add("sem-alvo");luz.style.left="50%";luz.style.top="50%";luz.style.width="0";luz.style.height="0";}
    var cw=card.offsetWidth,ch=card.offsetHeight,vw=window.innerWidth,vh=window.innerHeight,x,y;
    if(!r){x=(vw-cw)/2;y=(vh-ch)/2;}
    else{
      if(r.bottom+m+14+ch<vh){y=r.bottom+m+14;}else if(r.top-m-14-ch>0){y=r.top-m-14-ch;}else{y=Math.max(16,vh-ch-16);}
      x=Math.min(Math.max(16,r.left),vw-cw-16);
      if(r.width>vw*0.6&&r.height>vh*0.5){x=vw-cw-24;y=Math.max(16,vh-ch-24);}
    }
    card.style.left=x+"px";card.style.top=y+"px";
  }
  function mostrar(){
    var p=passos[i];alvo=p.alvo?document.querySelector(p.alvo):null;
    if(alvo)alvo.scrollIntoView({block:"center",behavior:"instant"});
    var pontos=passos.map(function(_,k){return"<i class='"+(k===i?"on":"")+"'></i>";}).join("");
    var ultimo=i===passos.length-1;
    card.innerHTML="<div class='tour-passo'>"+(p.tela||"Tour")+" · "+(i+1)+" de "+passos.length+"</div><h3>"+p.titulo+"</h3><p>"+p.texto+"</p>"+
      (p.sistema?"<div class='tour-sistema'><b>O sistema faz sozinho</b>"+p.sistema+"</div>":"")+
      "<div class='tour-acoes'><button class='tour-pular' type='button'>"+(ultimo?"":"Sair do tour")+"</button><span class='tour-pontos'>"+pontos+"</span><span>"+
      (i>0?"<button type='button' class='secundario tour-voltar'>Voltar</button> ":"")+
      "<button type='button' class='tour-prox'>"+(ultimo?(p.fim?"Concluir":"Entendi"):"Próximo")+"</button></span></div>";
    card.querySelector(".tour-prox").onclick=function(){if(ultimo){fechar(!!p.fim);}else{i++;mostrar();}};
    var v=card.querySelector(".tour-voltar");if(v)v.onclick=function(){i--;mostrar();};
    card.querySelector(".tour-pular").onclick=function(){fechar(true);};
    posicionar();setTimeout(posicionar,60);
  }
  function iniciar(manual){
    passos=ler();if(!passos.length)return;fechar(false);i=0;
    if(manual){ss("set",chave,"1");ss("set","tourVisto:"+(passos[0].tela||location.pathname),"1");}
    if(manual&&passos[0].inicio){try{Object.keys(sessionStorage).forEach(function(k){if(k.indexOf("tourVisto:")===0)sessionStorage.removeItem(k);});}catch(e){}}
    luz=document.createElement("div");luz.className="tour-luz";card=document.createElement("div");card.className="tour-card";
    document.body.appendChild(luz);document.body.appendChild(card);
    window.addEventListener("resize",posicionar);window.addEventListener("scroll",posicionar,true);
    document.addEventListener("keydown",function k(e){if(!card){document.removeEventListener("keydown",k);return;}
      if(e.key==="Escape")fechar(true);if(e.key==="ArrowRight"&&i<passos.length-1){i++;mostrar();}if(e.key==="ArrowLeft"&&i>0){i--;mostrar();}});
    mostrar();
  }
  document.addEventListener("DOMContentLoaded",function(){
    if(!document.getElementById("tour-passos")){var b=document.querySelector(".tour-btn");if(b)b.style.display="none";return;}
    var q=new URLSearchParams(location.search);
    var tela=(ler()[0]||{}).tela||location.pathname,visto="tourVisto:"+tela;
    // não abre sozinho; só continua uma jornada que a pessoa começou pelo botão (ou ?tour=1)
    if(q.get("tour")==="1"||(ss("get",chave)==="1"&&ss("get",visto)!=="1")){ss("set",visto,"1");iniciar(true);}
  });
  return{iniciar:iniciar,fechar:fechar};
})();
