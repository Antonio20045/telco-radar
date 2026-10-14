/* Telco Radar - Explorer (Vanilla JS, kein Framework) */

/* REDESIGN 09.10.2026 - Tageszeit, Auftritt, Szenen, Lesefluss, Suche.

   Steht GANZ OBEN, weil `data-zeit` gesetzt sein muss, bevor der Browser
   das erste Mal malt: an ihr haengen Farben und das Startbild. Alles hier
   ist Darstellung - keine Zahl entsteht im Browser; das Hochzaehlen einer
   Zahl im Bericht endet exakt beim Originaltext. Bewegung gibt es nur,
   wenn das System keine reduzierte Bewegung wuenscht. */
(function () {
  var wurzel = document.documentElement;
  wurzel.classList.remove('ohne-js');
  wurzel.classList.add('js');

  function tageszeit() {
    var h = new Date().getHours();
    if (h >= 5 && h < 10) return 'morgen';
    if (h >= 10 && h < 17) return 'tag';
    if (h >= 17 && h < 21) return 'abend';
    return 'nacht';
  }
  /* NUR TAG (Antonio, 10.10.2026): Farben und Startbild sind immer die
     Tagesansicht, egal wann gelesen wird. Die Uhrzeit waehlt nur noch den
     Gruss auf der Startseite. */
  var zeit = 'tag';
  var stunde = navigator.webdriver ? 'tag' : tageszeit();
  wurzel.setAttribute('data-zeit', zeit);

  var ruhig = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  if (!ruhig) wurzel.classList.add('bewegt');

  /* DIE BUEHNE: genau EIN Bild laden - das der Tageszeit. */
  var buehne = document.querySelector('.buehne');
  if (buehne) {
    var gruss = buehne.querySelector('[data-gruss]');
    var GRUSS = { morgen: 'Guten Morgen', tag: 'Guten Tag', abend: 'Guten Abend', nacht: 'Guten Abend' };
    if (gruss && gruss.textContent.trim() === 'Ausgabe') gruss.textContent = GRUSS[stunde];
    var ebenen = buehne.querySelectorAll('.buehne-ebene[data-zeit-bild]');
    var bild = null;
    for (var i = 0; i < ebenen.length; i++) {
      if (ebenen[i].getAttribute('data-zeit-bild') === zeit) bild = ebenen[i];
    }
    if (!bild && ebenen.length) bild = ebenen[0];
    /* Rechnet die Campus-Szene, steht bis zu ihrem ersten Bild kein Foto da:
       das Startfoto zeigt nur eine Lage und waere fast immer die falsche
       (Antonio, 14.10.2026). Es kommt nur, wenn die Szene nicht kann. */
    var szeneKommt = !!buehne.querySelector('.buehne-himmel') && !navigator.webdriver;
    if (szeneKommt) buehne.classList.add('campus-wartet', 'film-dunkel');
    var zeigeStartbild = function (src) {
      if (!bild) return;
      bild.classList.add('aktiv');
      bild.setAttribute('fetchpriority', 'high');
      bild.addEventListener('load', function () { bild.classList.add('geladen'); });
      if (src) bild.removeAttribute('srcset');
      else if (bild.getAttribute('data-srcset')) bild.srcset = bild.getAttribute('data-srcset');
      bild.src = src || bild.getAttribute('data-src');
      if (bild.complete && bild.naturalWidth) bild.classList.add('geladen');
    };
    if (!szeneKommt) zeigeStartbild(null);
    var stufen = buehne.querySelectorAll('.buehne-kopf > *, .fenster, .buehne-weiter');
    for (var s = 0; s < stufen.length; s++) {
      stufen[s].style.setProperty('--verzug', Math.min(s, 6) * 70 + 'ms');
    }
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { buehne.classList.add('buehne--da'); });
    });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (e) {
        buehne.classList.toggle('verdeckt', !e[0].isIntersecting);
      }).observe(buehne);
    }
  }

  /* Die Lage am Campus aus Zeitpunkt und Wetter: Sonnenhoehe, welche Platte
     wie stark, Laub der Jahreszeit und wie viele Bueros Licht haben. */
  var CAMPUS_LEBEN = (function () {
    var BREITE = 51.2437 * Math.PI / 180, LAENGE = 6.7383;
    var BUERO = [[0, 0.04], [5, 0.04], [6, 0.3], [7, 0.75], [8, 0.95], [17, 0.95], [18, 0.75], [19, 0.5],
      [20, 0.3], [21, 0.12], [22, 0.06], [24, 0.04]];
    /* Monat -> Laub [Fruehling, Herbst, Winter]; der Rest ist Sommer. */
    var LAUB = [[0, 0, 1], [0, 0, 1], [0.4, 0, 0.5], [1, 0, 0], [0.6, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0],
      [0, 0.35, 0], [0, 1, 0], [0, 0.7, 0.4], [0, 0, 1]];
    var JAHRESZEIT = ['winter', 'winter', 'fruehling', 'fruehling', 'fruehling', 'sommer', 'sommer', 'sommer',
      'herbst', 'herbst', 'herbst', 'winter'];
    var ORT = window.Intl ? new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Berlin', year: 'numeric', month: 'numeric',
      day: 'numeric', hour: 'numeric', minute: 'numeric', weekday: 'short', hourCycle: 'h23' }) : null;
    var kurve = function (punkte, x) {
      for (var i = 1; i < punkte.length; i++) {
        if (x <= punkte[i][0]) { var a = punkte[i - 1], b = punkte[i]; return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]); }
      }
      return punkte[punkte.length - 1][1];
    };
    var glatt = function (a, b, x) { var t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
    var buero = function (minute, werktag) {
      var v = kurve(BUERO, (((minute % 1440) + 1440) % 1440) / 60);
      return werktag ? v : Math.min(v, 0.07);
    };
    /* Uhrzeit, Datum und Wochentag in Duesseldorf */
    var ortszeit = function (d) {
      var t = {};
      if (ORT) ORT.formatToParts(d).forEach(function (p) { t[p.type] = p.value; });
      else t = { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), hour: d.getHours(), minute: d.getMinutes(),
        weekday: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()] };
      var tagNr = Math.round((Date.UTC(+t.year, +t.month - 1, +t.day) - Date.UTC(+t.year, 0, 1)) / 864e5) + 1;
      return { monat: +t.month - 1, tagNr: tagNr, minute: +t.hour * 60 + +t.minute, werktag: !/Sat|Sun/.test(t.weekday) };
    };
    /* Sonnenhoehe in Grad: Deklination aus dem Tag des Jahres, Stundenwinkel
       aus der wahren Ortszeit (Weltzeit, Laenge, Zeitgleichung). */
    var sonne = function (d, tagNr) {
      var dekl = 23.44 * Math.sin(2 * Math.PI / 365 * (tagNr - 81)) * Math.PI / 180;
      var b = 2 * Math.PI * (tagNr - 81) / 364;
      var gleichung = 9.87 * Math.sin(2 * b) - 7.53 * Math.cos(b) - 1.5 * Math.sin(b);
      var wahr = d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60 + LAENGE * 4 + gleichung;
      var winkel = (wahr - 720) / 4 * Math.PI / 180;
      var s = Math.sin(BREITE) * Math.sin(dekl) + Math.cos(BREITE) * Math.cos(dekl) * Math.cos(winkel);
      return Math.asin(s) * 180 / Math.PI;
    };
    /* Welche Fotoplatte wie stark: ueber 14 Grad Tag, bis -3,5 Grad goldene
       Stunde, bis -12 Grad blaue Stunde, darunter Nacht. */
    var platten = function (h) {
      var tag = glatt(3, 14, h), g1 = glatt(-3.5, 1.5, h), b1 = glatt(-12, -5.5, h);
      return [tag, (1 - tag) * g1, (1 - tag) * (1 - g1) * b1, (1 - tag) * (1 - g1) * (1 - b1)];
    };
    var lage = function (datum, wetter) {
      var o = ortszeit(datum), h = sonne(datum, o.tagNr), p = platten(h), laub = LAUB[o.monat];
      var w = wetter || { wolken: 0.5, regen: 0, schnee: 0, nebel: 0, wind: 0.2, gewitter: 0 };
      var wolken = Math.max(w.wolken, w.regen > 0.05 || w.schnee > 0.05 || w.nebel > 0.3 ? 0.92 : 0);
      var ziel = {
        tag: p[0], gold: p[1], blau: p[2], nacht: p[3], wolken: wolken, bedeckt: glatt(0.62, 0.95, wolken),
        regenPlatte: glatt(0.04, 0.25, w.regen), regenHell: (0.38 + 0.62 * glatt(-4, 12, h)) * (w.gewitter ? 0.7 : 1),
        regen: w.regen, schnee: w.schnee, nebel: w.nebel, wind: w.wind, gewitter: w.gewitter,
        decke: w.schnee > 0.05 ? 1 : 0, nass: w.regen > 0.05 ? 1 : 0,
        frueh: laub[0], herbst: laub[1], winter: laub[2], buero: buero(o.minute, o.werktag)
      };
      var NAMEN = ['tag', 'gold', 'blau', 'nacht'], staerkste = 0;
      for (var i = 1; i < 4; i++) if (p[i] > p[staerkste]) staerkste = i;
      return {
        ziel: ziel, sonne: h, jahreszeit: JAHRESZEIT[o.monat],
        szene: NAMEN[staerkste] + '-' + (wetter ? w.wort.toLowerCase() : 'unbekannt'),
        hell: h > 6 && wolken < 0.85 && w.regen < 0.05 && w.nebel < 0.5
      };
    };
    return { lage: lage, buero: buero };
  })();

  /* Der Shader: Platten nach Gewicht, Laub, Wolken ueber dem echten Himmel,
     nasser Platz, Schneedecke, Leuchthof, Flugwarnlichter, Nebel, Niederschlag. */
  var CAMPUS_SHADER = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 farbe;
uniform sampler2D uTag, uGold, uBlau, uNacht, uSpaet, uRegen, uSchneeP, uMA, uMB, uGlanz, uHim;
uniform vec4 uW;            // Tag, Gold, Blau, Nacht (Summe 1)
uniform float uRegenPlatte; // Anteil der Regenplatte an Tag und Gold
uniform float uBedeckt;     // geschlossene Wolkendecke 0..1
uniform float uRegenHell;   // Helligkeit der Regenplatte nach Sonnenstand
uniform vec2 uAufl, uBild, uAnker;
uniform float uZeit, uWolken, uRegenI, uSchnee, uDecke, uNebel, uWind, uBlitz, uHerbst, uWinter, uFrueh, uNass, uBuero;

float hash(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}
float noise(vec2 p){vec2 i=floor(p);vec2 f=fract(p);f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){float v=0.0;float a=0.5;for(int i=0;i<5;i++){v+=a*noise(p);p=p*2.03+vec2(1.7,9.2);a*=0.5;}return v;}
float lum(vec3 c){return dot(c,vec3(0.2126,0.7152,0.0722));}

// Bildausschnitt wie object-fit:cover mit object-position uAnker, genau wie das Startfoto darunter
vec2 cover(vec2 s){
  float ab=uAufl.x/uAufl.y, ai=uBild.x/uBild.y; vec2 k=vec2(1.0), m=vec2(0.5);
  if(ab>ai){k.y=ai/ab;m.y=k.y*0.5+uAnker.y*(1.0-k.y);}else{k.x=ab/ai;m.x=k.x*0.5+uAnker.x*(1.0-k.x);}
  return m+(s-0.5)*k;
}
vec3 kachel(sampler2D t,vec2 u,float i,float n,float h){float y=clamp(u.y,1.5/h,1.0-1.5/h);return texture(t,vec2(u.x,(i+y)/n)).rgb;}

void main(){
  vec2 u0=cover(vUv);
  float wT=uW.x,wG=uW.y,wB=uW.z,wN=uW.w;
  float dunkel=clamp(wN+wB*0.75+wG*0.25,0.0,1.0);

  // Wind in den Kronen: weich ausgeblendete Verschiebung, Boeen kommen und gehen, die Blaetter zittern
  vec2 u=u0;
  float weich=textureLod(uMA,u0,3.0).g;
  if(weich>0.002){
    float t=uZeit;float boe=0.5+0.5*sin(t*0.29+2.0*sin(t*0.11));
    float ph=noise(u0*vec2(14.0,9.0))*6.283;
    float sw=sin(t*(0.8+0.9*uWind)+ph)+0.4*sin(t*(2.1+1.6*uWind)+ph*1.7);
    float zit=noise(u0*vec2(300.0,210.0)+vec2(t*(1.4+3.5*uWind),t*0.8))-0.5;
    vec2 d=vec2(sw*(0.5+4.5*uWind)*(0.4+0.6*boe)+zit*(0.6+2.2*uWind),0.22*sw*(0.3+uWind)+zit*0.4);
    u=u0+d*weich/uBild;
  }
  vec3 ma=texture(uMA,u).rgb;   // r Himmel, g Baum, b Boden
  float himmel=ma.r, baum=ma.g, boden=ma.b;

  // Bedeckt ohne Regen: Gebaeude im weichen Licht der Regenplatte, der trockene Platz bleibt aus der Tagplatte
  float r=max(uRegenPlatte,uBedeckt*(1.0-boden));
  float wR=(wT+wG)*r; wT*=1.0-r; wG*=1.0-r;
  // Schneedecke bei Tag: echte Winterplatte
  float wS=(wT+wG+wR)*uDecke; wT*=1.0-uDecke; wG*=1.0-uDecke; wR*=1.0-uDecke;
  float deckeRest=uDecke*(1.0-(uW.x+uW.y));

  vec3 I=vec3(0.0), S=vec3(0.0), G=vec3(0.0);
  float an=uBuero;
  if(wT>0.001){I+=wT*texture(uTag,u).rgb;S+=wT*kachel(uHim,u,0.0,7.0,266.0);}
  if(wG>0.001){I+=wG*texture(uGold,u).rgb;S+=wG*kachel(uHim,u,1.0,7.0,266.0);}
  if(wB>0.001){I+=wB*texture(uBlau,u).rgb;S+=wB*kachel(uHim,u,2.0,7.0,266.0);G+=wB*0.55*kachel(uGlanz,u,2.0,3.0,531.0);}
  if(wN>0.001){
    // Buerolichter: jedes Fenster hat eine eigene Schwelle; liegt der Anteil besetzter Bueros darueber, brennt es
    vec3 mb=texture(uMB,u).rgb;
    an=mix(clamp(uBuero*1.15,0.0,1.0),smoothstep(mb.g-0.025,mb.g+0.025,uBuero*1.15),mb.b);
    vec3 n=texture(uNacht,u).rgb, s=texture(uSpaet,u).rgb;
    I+=wN*mix(s,n,an);S+=wN*kachel(uHim,u,4.0,7.0,266.0);
    G+=wN*mix(kachel(uGlanz,u,1.0,3.0,531.0),kachel(uGlanz,u,0.0,3.0,531.0),clamp(uBuero*1.6,0.0,1.0));
  }
  if(wR>0.001){I+=wR*texture(uRegen,u).rgb*uRegenHell;S+=wR*kachel(uHim,u,5.0,7.0,266.0)*uRegenHell;}
  if(wS>0.001){I+=wS*texture(uSchneeP,u).rgb*uRegenHell;S+=wS*kachel(uHim,u,6.0,7.0,266.0)*uRegenHell;}

  // Jahreszeit im Laub (das Foto zeigt Herbst)
  if(baum>0.01){
    float l=lum(I);float v=noise(u*vec2(20.0,14.0));
    vec3 frueh=mix(vec3(0.42,0.60,0.18),vec3(0.55,0.68,0.26),v);
    vec3 sommer=mix(vec3(0.17,0.30,0.09),vec3(0.24,0.36,0.11),v);
    float som=clamp(1.0-uFrueh-uHerbst-uWinter,0.0,1.0);
    vec3 ziel=frueh*uFrueh+sommer*som;
    float st=uFrueh+som;
    vec3 neu=ziel/max(lum(ziel),0.02)*l*mix(1.0,1.12,uFrueh);
    I=mix(I,mix(neu,vec3(l),0.06),baum*st*0.9);
    // Winter: kahl, braungrau, gegen den Himmel licht
    vec3 kahl=vec3(l)*vec3(0.86,0.79,0.72)*0.8;
    float nah=smoothstep(0.1,0.5,textureLod(uMA,u,5.5).r);
    kahl=mix(kahl,S,0.28*nah);
    I=mix(I,kahl,baum*uWinter*(1.0-wS));
  }

  vec3 col=I;

  // Wolken ueber dem echten Himmel; an Kanten mit der Himmelsschaetzung entmischt, damit kein Saum entsteht
  float opaz=1.0-(uW.x+uW.y)*max(uRegenPlatte,uBedeckt);
  if(himmel>0.002&&uWolken>0.02&&opaz>0.01){
    float hor=0.74;float e=max(hor-u0.y,0.0);float t=1.0/(e+0.11);
    float wind=uZeit*(0.005+0.024*uWind);
    vec2 p=vec2((u0.x-0.5)*1.6*t+wind*t*0.28,t*1.3+wind*0.12);
    vec2 q=vec2(fbm(p*0.6),fbm(p*0.6+vec2(5.2,1.3)));
    float d=fbm(p*0.85+q*0.7);
    float c=min(clamp(uWolken,0.0,1.0),0.72);
    float dichte=smoothstep(0.80-c*0.64,0.97-c*0.50,d)*smoothstep(0.0,0.07,e);
    float d2=fbm(p*0.85+q*0.7+vec2(0.07,-0.11));
    float hell=clamp(0.55+1.8*(d-d2),0.0,1.0);
    vec3 lichtC=uW.x*vec3(0.97,0.97,0.98)+uW.y*vec3(1.0,0.76,0.60)+uW.z*vec3(0.58,0.52,0.64)+uW.w*vec3(0.15,0.115,0.105);
    vec3 schattenC=uW.x*vec3(0.60,0.63,0.69)+uW.y*vec3(0.46,0.38,0.46)+uW.z*vec3(0.25,0.24,0.33)+uW.w*vec3(0.045,0.04,0.045);
    vec3 grau=(uW.x+uW.y*0.7+uW.z*0.3+uW.w*0.07)*vec3(0.66,0.68,0.71)*(1.0-0.35*uRegenI);
    lichtC=mix(lichtC,grau*1.08,uBedeckt*0.85);schattenC=mix(schattenC,grau*0.72,uBedeckt*0.85);
    vec3 wc=mix(schattenC,lichtC,hell);
    wc=mix(S,wc,smoothstep(0.0,0.45,dichte));
    vec3 neuHimmel=mix(S,wc,clamp(dichte*1.15,0.0,1.0)*opaz);
    // geschlossene Decke: weich, unten von der Stadt angeleuchtet
    float decke=smoothstep(0.62,0.95,uWolken);
    if(decke>0.0){
      float hh=pow(clamp((hor+0.08-u0.y)/(hor+0.08),0.0,1.0),0.7);
      vec3 strH=uW.x*vec3(0.74,0.76,0.79)+uW.y*vec3(0.66,0.58,0.56)+uW.z*vec3(0.36,0.35,0.43)+uW.w*vec3(0.14,0.115,0.105);
      vec3 strO=uW.x*vec3(0.60,0.62,0.66)+uW.y*vec3(0.44,0.42,0.47)+uW.z*vec3(0.21,0.21,0.28)+uW.w*vec3(0.05,0.047,0.055);
      vec3 str=mix(strH,strO,hh)*(1.0-0.3*uRegenI);
      float tex=fbm(vec2(u0.x*2.4+wind*0.6,u0.y*4.5))*0.6+fbm(vec2(u0.x*7.0+wind*1.2,u0.y*12.0))*0.4;
      str*=0.86+0.26*tex;
      neuHimmel=mix(neuHimmel,str,decke*opaz);
    }
    col=col+himmel*(neuHimmel-S);
  }

  // Nasser Platz ohne Regenplatte (Abend, Nacht): Spiegelung der Gebaeudesockel, gekraeuselt
  float nassOhne=uNass*(1.0-uRegenPlatte*(uW.x+uW.y));
  if(nassOhne>0.01&&boden>0.01){
    float yb=0.866;
    float rip=(noise(vec2(u0.x*90.0,u0.y*260.0+uZeit*0.8))-0.5)*0.0018*(0.4+uRegenI);
    vec2 rr=vec2(u0.x+rip,2.0*yb-u0.y);
    vec3 sp=vec3(0.0);
    for(int k=0;k<3;k++){
      vec2 rk=rr+vec2(0.0,float(k)*0.006*(u0.y-yb)*4.0);
      if(uW.z>0.001)sp+=uW.z*textureLod(uBlau,rk,2.2).rgb;
      if(uW.w>0.001)sp+=uW.w*mix(textureLod(uSpaet,rk,2.2).rgb,textureLod(uNacht,rk,2.2).rgb,an);
      if(uW.x+uW.y>0.001)sp+=(uW.x+uW.y)*textureLod(uTag,rk,2.2).rgb;
    }
    sp/=3.0;
    float fres=1.0-smoothstep(yb,1.0,u0.y)*0.45;
    float hellig=smoothstep(0.12,0.7,lum(sp));
    col=col*mix(1.0,0.74,nassOhne*boden)+sp*boden*nassOhne*fres*(0.10+0.75*hellig);
  }

  // Schneedecke auf Platz, Hecken und Kronen
  if(deckeRest>0.01){
    float licht=uW.z*0.40+uW.w*0.10;
    vec3 sc=vec3(0.80,0.84,0.95)*licht+vec3(0.05,0.055,0.08);
    sc+=I*0.9;
    float wellig=0.92+0.10*noise(u0*vec2(30.0,80.0));
    float auf=boden*0.92+baum*0.35;
    col=mix(col,sc*wellig,clamp(auf,0.0,1.0)*deckeRest);
  }

  // Leuchten in der Daemmerung und Nacht: Hof um Logo, Fenster und Laternen; rote Flugwarnlichter blinken
  col+=G*(0.30+0.9*uNebel)*dunkel;
  {
    float zyk=mod(uZeit,3.0);float blink=step(zyk,1.0)+step(1.5,zyk)*step(zyk,2.0);
    vec2 P=u0*uBild;float fw=0.0;
    fw+=exp(-pow(length(P-vec2(0.3880,0.0432)*uBild)/5.0,2.0))+exp(-length(P-vec2(0.3880,0.0432)*uBild)/16.0)*0.25;
    fw+=exp(-pow(length(P-vec2(0.3982,0.0786)*uBild)/5.0,2.0))+exp(-length(P-vec2(0.3982,0.0786)*uBild)/16.0)*0.25;
    fw+=(exp(-pow(length(P-vec2(0.3976,0.1710)*uBild)/4.0,2.0))+exp(-pow(length(P-vec2(0.3880,0.1806)*uBild)/4.0,2.0)))*0.6;
    col+=vec3(1.0,0.12,0.06)*fw*blink*smoothstep(0.3,0.8,dunkel)*0.9;
  }

  // Nebel: Ferne dichter, Lichter leuchten hindurch
  if(uNebel>0.01){
    float tiefe=max(mix(0.12,1.0,smoothstep(0.98,0.40,u0.y)),himmel);
    float n=fbm(vec2(u0.x*2.2+uZeit*0.012,u0.y*3.5-uZeit*0.003))*0.65+fbm(vec2(u0.x*7.0-uZeit*0.02,u0.y*9.0))*0.35;
    vec3 nf=uW.x*vec3(0.78,0.80,0.83)+uW.y*vec3(0.80,0.72,0.66)+uW.z*vec3(0.40,0.42,0.50)+uW.w*vec3(0.10,0.095,0.10);
    nf=mix(nf,vec3(lum(nf)),0.25);
    col=mix(col,nf,clamp(uNebel*tiefe*(0.55+0.6*n),0.0,0.92));
    col+=G*uNebel*dunkel*0.7;
  }

  // Niederschlag
  vec2 q=vUv*vec2(uAufl.x/uAufl.y,1.0);
  if(uRegenI>0.01){
    col=mix(col,vec3(lum(col))*vec3(0.95,0.97,1.0),0.18*uRegenI);
    float a=0.0;
    for(int l=0;l<3;l++){
      float fl=float(l);float sk=34.0+fl*26.0;
      vec2 g=q*vec2(sk,sk*0.11);g.x+=g.y*(0.03+0.20*uWind);g.y+=uZeit*(8.0+fl*3.5);
      vec2 i=floor(g);vec2 f=fract(g);float h=hash(i+fl*17.0);
      float x=abs(f.x-0.15-0.7*h);
      float st=smoothstep(0.045-fl*0.01,0.0,x)*smoothstep(0.0,0.35,f.y)*smoothstep(1.0,0.55,f.y);
      a+=st*step(1.0-uRegenI*0.6,h)*(0.55-fl*0.13);
    }
    vec3 rc=vec3(0.78,0.81,0.86)*(0.35+0.65*(1.0-dunkel))+G*1.2+vec3(0.08)*dunkel;
    col=mix(col,rc,clamp(a,0.0,1.0)*0.34);
  }
  if(uSchnee>0.01){
    float a=0.0;
    for(int l=0;l<4;l++){
      float fl=float(l);float sk=26.0-fl*5.0;
      vec2 g=q*sk;g.y-=uZeit*(0.06+0.045*fl)*sk*0.4;g.x+=sin(uZeit*0.55+g.y*0.6+fl*2.0)*0.32+uZeit*uWind*0.06*sk;
      vec2 i=floor(g);vec2 f=fract(g)-0.5;float h=hash(i+fl*31.0);
      vec2 o=vec2(h-0.5,hash(i+7.0)-0.5)*0.6;float d=length(f-o);
      float gr=mix(0.028,0.06,fl/3.0);float rand=mix(0.012,0.06,fl/3.0);
      a+=smoothstep(gr+rand,gr-rand*0.6,d)*step(1.0-uSchnee*(0.55-fl*0.08),h)*mix(0.8,0.35,fl/3.0);
    }
    vec3 fc=vec3(0.95,0.96,1.0)*(0.42+0.58*(1.0-dunkel))+G*0.8;
    col=mix(col,fc,clamp(a,0.0,1.0));
  }
  col+=vec3(0.62,0.66,0.82)*uBlitz*(0.22+0.78*himmel);

  // Film: sanfte Kurve, Vignette, feines Korn
  col=max(col,0.0);
  col=mix(col,col*col*(3.0-2.0*col),0.10);
  vec2 v=vUv-0.5;col*=1.0-0.20*dot(v,v)*1.6;
  col+=(hash(floor(gl_FragCoord.xy)+fract(uZeit*24.0)*vec2(113.0,71.0))-0.5)*0.012;
  farbe=vec4(clamp(col,0.0,1.0),1.0);
}`;


  /* DER CAMPUS LEBT (Antonio, 13.10.2026): hinter der Buehne stehen sieben
     echte Fotoplatten des Turms im selben Blickwinkel - Tag, goldene Stunde,
     blaue Stunde, Abend mit Licht, spaete Nacht, Regen, Schnee. Ein
     WebGL-2-Canvas blendet zwischen ihnen nach der Sonnenhoehe am Campus,
     legt Wolken, Regen, Schnee, Nebel und Wind darueber und schaltet nachts
     die Bueros Fenster fuer Fenster nach der Belegung (CAMPUS_LEBEN). Es zaehlt
     die echte Zeit in Duesseldorf, nicht die des Lesers. Das Wetter kommt
     ohne Schluessel und ohne Kosten von Open-Meteo (Daten u. a. des Deutschen
     Wetterdienstes); antwortet der Dienst nicht, bleibt der Himmel bewoelkt
     und es steht keine Wetterzeile da. Die Szene erscheint erst mit ihrem
     ersten Bild in der echten Lage, ohne Startfoto davor und ohne
     Ueberblenden aus einer anderen Lage (Antonio, 14.10.2026); geladen wird
     nur, was die Lage braucht. Ohne WebGL 2 steht das Foto der Platte, die
     zur Uhrzeit passt; unter Automatisierung bleibt die Buehne ruhig. */
  var himmelBild = buehne && buehne.querySelector('.buehne-himmel');
  if (himmelBild && !navigator.webdriver) {
    var CAMPUS = 'https://api.open-meteo.com/v1/forecast?latitude=51.2437&longitude=6.7383'
      + '&current=weather_code,temperature_2m,cloud_cover,wind_speed_10m&timezone=Europe%2FBerlin&forecast_days=1';
    var REGEN = { 51: 0.3, 53: 0.4, 55: 0.5, 56: 0.4, 57: 0.5, 61: 0.45, 63: 0.6, 65: 0.85, 66: 0.5, 67: 0.75,
      80: 0.45, 81: 0.65, 82: 0.9, 95: 1, 96: 1, 99: 1 };
    var SCHNEE = { 71: 0.45, 73: 0.65, 75: 0.9, 77: 0.3, 85: 0.55, 86: 0.9 };
    var wetterAus = function (c) {
      var code = c.weather_code;
      var w = {
        wolken: typeof c.cloud_cover === 'number' ? c.cloud_cover / 100 : (code >= 3 ? 0.95 : code >= 2 ? 0.5 : 0.15),
        regen: REGEN[code] || 0, schnee: SCHNEE[code] || 0, nebel: code === 45 || code === 48 ? 0.8 : 0,
        wind: Math.min(1, (typeof c.wind_speed_10m === 'number' ? c.wind_speed_10m : 10) / 50), gewitter: code >= 95 ? 1 : 0
      };
      w.wort = w.gewitter ? 'Gewitter' : w.schnee ? 'Schnee' : w.regen ? 'Regen' : w.nebel ? 'Nebel'
        : w.wolken > 0.7 ? 'bedeckt' : w.wolken > 0.4 ? 'bewölkt' : 'klar';
      w.grad = typeof c.temperature_2m === 'number' ? Math.round(c.temperature_2m) : null;
      return w;
    };
    var zeigeLage = function (wetter) {
      var l = CAMPUS_LEBEN.lage(new Date(), wetter);
      himmelBild.setAttribute('data-szene', l.szene);
      himmelBild.setAttribute('data-jahreszeit', l.jahreszeit);
      himmelBild.setAttribute('data-sonne', String(Math.round(l.sonne)));
      himmelBild.setAttribute('data-buero', String(Math.round(l.ziel.buero * 100)));
      buehne.classList.toggle('film-dunkel', !l.hell);
      return l;
    };
    /* Das Wetter bekommt hoechstens WETTER_FRIST ms; danach zeichnet die
       Szene die Lage ohne Wetter, statt den Leser warten zu lassen. */
    var WETTER_FRIST = 1500;
    var spaeter = window.fetch ? Promise.race([
      fetch(CAMPUS).then(function (a) {
        if (!a.ok) throw new Error('Wetter ' + a.status);
        return a.json();
      }),
      new Promise(function (_, nein) { setTimeout(function () { nein(new Error('Wetter zu langsam')); }, WETTER_FRIST); })
    ]) : Promise.reject(new Error('kein fetch'));
    var gross = Math.max(screen.width, window.innerWidth) * (window.devicePixelRatio || 1) > 2700;
    var ohneWetter = CAMPUS_LEBEN.lage(new Date(), null);
    /* Kann die Szene nicht, steht das Foto der Platte, die der Uhrzeit am
       naechsten kommt; die blaue 2K-Platte ist das Startfoto. */
    var ersatz = function () {
      buehne.classList.remove('campus-wartet');
      var platte = ohneWetter.szene.split('-')[0];
      zeigeStartbild(platte === 'blau' ? null : himmelBild.getAttribute('data-basis') + '2k/platte-' + platte + '.jpg');
    };
    var szene = campusSzene(himmelBild, gross, ohneWetter.ziel, ruhig, ersatz);
    if (!szene) ersatz();
    spaeter.then(function (d) { return wetterAus(d.current || {}); }, function () { return null; }).then(function (wetter) {
      var l = zeigeLage(wetter);
      var zeile = document.querySelector('[data-campus-wetter]');
      if (zeile && wetter) {
        zeile.textContent = 'Campus Düsseldorf · ' + (wetter.grad == null ? '' : wetter.grad + ' °C, ') + wetter.wort;
        zeile.hidden = false;
      }
      if (!szene) return;
      szene.start(l.ziel, function () { buehne.classList.remove('campus-wartet'); });
      setInterval(function () { szene.neu(zeigeLage(wetter).ziel); }, 5 * 60 * 1000);
    });
  }

  /* Die Szene selbst. Jede Platte bekommt ihre feste Texture-Einheit; was die
     Lage nicht braucht, wird nicht geladen und vom Shader nicht gelesen. Die
     Platten der Lage ohne Wetter (vorab) laden sofort; start(ziel, fertig)
     malt das erste Bild gleich in der echten Lage. Scheitert das Laden, ruft
     die Szene fehlt(). Gibt { start, neu } zurueck oder null. */
  function campusSzene(canvas, gross, vorab, still, fehlt) {
    var gl = canvas.getContext('webgl2', { alpha: false, antialias: false, depth: false, powerPreference: 'high-performance' });
    if (!gl) return null;
    var VS = '#version 300 es\nin vec2 p;out vec2 vUv;void main(){vUv=p*0.5+0.5;vUv.y=1.0-vUv.y;gl_Position=vec4(p,0.0,1.0);}';
    var prog = gl.createProgram();
    var teil = function (typ, quelle) {
      var s = gl.createShader(typ);
      gl.shaderSource(s, quelle);
      gl.compileShader(s);
      gl.attachShader(prog, s);
      return gl.getShaderParameter(s, gl.COMPILE_STATUS);
    };
    if (!teil(gl.VERTEX_SHADER, VS) || !teil(gl.FRAGMENT_SHADER, CAMPUS_SHADER)) return null;
    gl.bindAttribLocation(prog, 0, 'p');
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    var U = {};
    ['uTag', 'uGold', 'uBlau', 'uNacht', 'uSpaet', 'uRegen', 'uSchneeP', 'uMA', 'uMB', 'uGlanz', 'uHim', 'uW', 'uRegenPlatte',
      'uBedeckt', 'uRegenHell', 'uAufl', 'uBild', 'uAnker', 'uZeit', 'uWolken', 'uRegenI', 'uSchnee', 'uDecke', 'uNebel', 'uWind',
      'uBlitz', 'uHerbst', 'uWinter', 'uFrueh', 'uNass', 'uBuero'].forEach(function (n) { U[n] = gl.getUniformLocation(prog, n); });
    /* Grosse Bildschirme (ab 2700 physischen Pixeln) bekommen die 4K-Platten,
       alle anderen die 2,5K-Platten; die blaue 2K-Platte ist das Startfoto. */
    var basis = canvas.getAttribute('data-basis'), satz = basis + (gross ? '4k/' : '2k/');
    var PLATTEN = {
      uTag: [satz + 'platte-tag.jpg', 1], uGold: [satz + 'platte-gold.jpg', 1],
      uBlau: [gross ? satz + 'platte-blau.jpg' : canvas.getAttribute('data-blau'), 1],
      uNacht: [satz + 'platte-nacht.jpg', 1], uSpaet: [satz + 'platte-spaet.jpg', 1], uRegen: [satz + 'platte-regen.jpg', 1],
      uSchneeP: [satz + 'platte-schnee.jpg', 1], uMA: [satz + 'maske-a.png', 1], uMB: [basis + 'maske-b.png', 0],
      uGlanz: [basis + 'glanz.png', 0], uHim: [basis + 'himmel-atlas.png', 0]
    };
    var einheiten = Object.keys(PLATTEN), geladen = {};
    var leer = gl.createTexture();
    einheiten.forEach(function (n, i) {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, leer);
      gl.uniform1i(U[n], i);
    });
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, 1, 1, 0, gl.RGB, gl.UNSIGNED_BYTE, new Uint8Array(3));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    var aniso = gl.getExtension('EXT_texture_filter_anisotropic');
    var bildW = 3840, bildH = 2124;
    var lade = function (n) {
      if (!geladen[n]) geladen[n] = new Promise(function (ok, fehler) {
        var b = new Image();
        b.decoding = 'async';
        b.onload = function () {
          gl.activeTexture(gl.TEXTURE0 + einheiten.indexOf(n));
          gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
          gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB8, gl.RGB, gl.UNSIGNED_BYTE, b);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          if (PLATTEN[n][1]) {
            gl.generateMipmap(gl.TEXTURE_2D);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
            if (aniso) gl.texParameterf(gl.TEXTURE_2D, aniso.TEXTURE_MAX_ANISOTROPY_EXT, Math.min(8, gl.getParameter(aniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
          } else gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          if (/^u(Tag|Gold|Blau|Nacht|Spaet|Regen|SchneeP)$/.test(n)) { bildW = b.naturalWidth; bildH = b.naturalHeight; }
          ok();
        };
        b.onerror = function () { fehler(new Error(PLATTEN[n][0])); };
        b.src = PLATTEN[n][0];
      });
      return geladen[n];
    };
    /* Was eine Lage liest. */
    var bedarf = function (z) {
      var n = ['uMA', 'uHim', 'uGlanz'], hell = z.tag + z.gold > 0.001;
      if (hell) n.push('uTag');
      if (z.blau > 0.001) n.push('uBlau');
      if (z.gold > 0.001) n.push('uGold');
      if (z.nacht > 0.001) n.push('uNacht', 'uSpaet', 'uMB');
      if (hell && Math.max(z.regenPlatte, z.bedeckt) > 0.001) n.push('uRegen');
      if (hell && z.decke > 0.001) n.push('uSchneeP');
      return Promise.all(n.map(lade));
    };
    var jetzt = {}, soll = {};
    bedarf(vorab).catch(function () {});
    var t0 = 0, letzte = 0, gemalt = 0, blitz = 0, naechster = 3, skala = 1, langsam = 0;
    var laeuft = false, sichtbar = true, raf = 0;
    var male = function (zeit) {
      var echt = Math.max(0, (zeit - letzte) / 1000), dt = Math.min(0.1, echt);
      letzte = zeit;
      var sek = (zeit - t0) / 1000 + 20;
      var tempo = Math.min(1, echt * 0.9);
      for (var j in soll) jetzt[j] += (soll[j] - jetzt[j]) * tempo;
      if (soll.gewitter && !still) {
        naechster -= dt;
        if (naechster <= 0) { blitz = 1; naechster = 3 + Math.random() * 7; }
      }
      blitz *= Math.pow(0.015, dt);
      var dpr = (window.devicePixelRatio || 1) * skala;
      var w = Math.max(1, Math.round(canvas.clientWidth * dpr)), h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      var deckel = Math.min(1, bildW / w, bildH * 1.15 / h);
      w = Math.round(w * deckel);
      h = Math.round(h * deckel);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      gl.viewport(0, 0, w, h);
      var summe = jetzt.tag + jetzt.gold + jetzt.blau + jetzt.nacht || 1;
      gl.uniform4f(U.uW, jetzt.tag / summe, jetzt.gold / summe, jetzt.blau / summe, jetzt.nacht / summe);
      gl.uniform1f(U.uRegenPlatte, jetzt.regenPlatte);
      gl.uniform1f(U.uBedeckt, jetzt.bedeckt);
      gl.uniform1f(U.uRegenHell, jetzt.regenHell);
      gl.uniform2f(U.uAufl, w, h);
      gl.uniform2f(U.uBild, bildW, bildH);
      /* Wie object-position des Startfotos in style.css: breit Turm links und
         Datum vor freiem Himmel, hoch Turm in der Mitte. */
      if (w / h > 1.2) gl.uniform2f(U.uAnker, 0.5, 0.25);
      else gl.uniform2f(U.uAnker, 0.24, 0.25);
      gl.uniform1f(U.uZeit, still ? 20 : sek);
      gl.uniform1f(U.uBlitz, Math.max(0, blitz * (0.55 + 0.45 * Math.sin(sek * 47) * Math.sin(sek * 13))));
      gl.uniform1f(U.uWolken, jetzt.wolken);
      gl.uniform1f(U.uRegenI, jetzt.regen);
      gl.uniform1f(U.uSchnee, jetzt.schnee);
      gl.uniform1f(U.uDecke, jetzt.decke);
      gl.uniform1f(U.uNebel, jetzt.nebel);
      gl.uniform1f(U.uWind, jetzt.wind);
      gl.uniform1f(U.uHerbst, jetzt.herbst);
      gl.uniform1f(U.uWinter, jetzt.winter);
      gl.uniform1f(U.uFrueh, jetzt.frueh);
      gl.uniform1f(U.uNass, jetzt.nass);
      gl.uniform1f(U.uBuero, jetzt.buero);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
    /* Hoechstens 30 Bilder je Sekunde; ruckelt es lange, rechnet die Szene kleiner. */
    var schleife = function (zeit) {
      if (!laeuft) return;
      raf = requestAnimationFrame(schleife);
      if (zeit - gemalt < 32) return;
      langsam = zeit - gemalt > 70 ? langsam + 1 : 0;
      if (langsam > 30 && skala > 0.6) { skala *= 0.85; langsam = 0; }
      gemalt = zeit;
      male(zeit);
    };
    var steuere = function () {
      var an = !still && !document.hidden && sichtbar;
      if (an && !laeuft) { laeuft = true; letzte = gemalt = performance.now(); raf = requestAnimationFrame(schleife); }
      if (!an && laeuft) { laeuft = false; cancelAnimationFrame(raf); }
    };
    return {
      start: function (ziel, fertig) {
        for (var k in ziel) { jetzt[k] = ziel[k]; soll[k] = ziel[k]; }
        bedarf(ziel).then(function () {
          t0 = letzte = performance.now();
          male(t0);
          var w = [jetzt.tag, jetzt.gold, jetzt.blau, jetzt.nacht], st = 0;
          for (var i = 1; i < 4; i++) if (w[i] > w[st]) st = i;
          canvas.setAttribute('data-erstes-bild', ['tag', 'gold', 'blau', 'nacht'][st]);
          canvas.classList.add('laeuft');
          fertig();
          steuere();
          document.addEventListener('visibilitychange', steuere);
          if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (e) { sichtbar = e[0].isIntersecting; steuere(); }).observe(canvas);
          }
          window.addEventListener('resize', function () { if (still) male(performance.now()); });
        }).catch(fehlt);
      },
      neu: function (z) {
        bedarf(z).then(function () {
          for (var j in z) soll[j] = z[j];
          if (still) { for (var i in z) jetzt[i] = z[i]; male(performance.now()); }
        }).catch(function () {});
      }
    };
  }

  /* DER KOPF wird beim Scrollen etwas deckender. */
  var kopf = document.getElementById('kopf');
  if (kopf) {
    var rolle = function () { kopf.classList.toggle('kopf--gerollt', window.scrollY > 24); };
    window.addEventListener('scroll', rolle, { passive: true });
    rolle();
  }

  /* ⌘K / Strg+K setzt den Fokus in die Suche. */
  var taste = document.querySelector('.gsearch-taste');
  if (taste && !/Mac|iPhone|iPad/.test(navigator.platform || '')) taste.textContent = 'Strg K';
  document.addEventListener('keydown', function (ev) {
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === 'k' || ev.key === 'K')) {
      var feld = document.getElementById('gsearch-input') || document.querySelector('input[type="search"]');
      if (feld) { ev.preventDefault(); feld.focus(); if (feld.select) feld.select(); }
    }
  });

  /* ZAHLEN zaehlen einmal kurz hoch und enden beim Originaltext. */
  function zaehle(el) {
    if (ruhig || !window.Intl) return;
    var werte = el.classList && el.classList.contains('zahl-wert') ? [el] : el.querySelectorAll('.zahl-wert');
    for (var i = 0; i < werte.length; i++) (function (z) {
      if (z.getAttribute('data-gezaehlt')) return;
      z.setAttribute('data-gezaehlt', '1');
      var ziel = parseFloat(z.getAttribute('data-wert'));
      var stellen = parseInt(z.getAttribute('data-stellen') || '0', 10);
      if (!isFinite(ziel) || ziel < 10) return;
      var original = z.textContent;
      var fmt = new Intl.NumberFormat('de-DE', { minimumFractionDigits: stellen, maximumFractionDigits: stellen });
      z.style.display = 'inline-block';
      z.style.minWidth = z.getBoundingClientRect().width + 'px';
      var start = null;
      var DAUER = 900;
      function schritt(t) {
        if (start === null) start = t;
        var p = Math.min(1, (t - start) / DAUER);
        z.textContent = fmt.format(ziel * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(schritt);
        else z.textContent = original;
      }
      requestAnimationFrame(schritt);
    })(werte[i]);
  }

  /* LESEFLUSS: Absaetze und Aufzaehlungen erscheinen, wenn der Leser sie
     erreicht - einmal, dann bleiben sie. Was beim Laden schon im Bild ist,
     wird nie versteckt. */
  /* Der Wochenbericht steht seit 14.10.2026 sofort da (Antonio: "der
     Bericht ... zu viel Bewegung"); eingeblendet wird nur noch, was eine
     Seite ausdruecklich mit data-auftritt markiert. */
  var LESESTUECKE = '[data-auftritt]';
  var lesen = null;
  function aufdecken(el, sofort) {
    if (!el.classList.contains('vorher') || el.classList.contains('sichtbar')) return;
    if (sofort) el.style.transition = 'none';
    el.classList.add('sichtbar');
    if (lesen) lesen.unobserve(el);
    if (!sofort) zaehle(el);
  }
  function alleBis(ziel) {
    var stuecke = document.querySelectorAll('.vorher:not(.sichtbar)');
    for (var i = 0; i < stuecke.length; i++) {
      var lage = ziel.compareDocumentPosition(stuecke[i]);
      if (lage & Node.DOCUMENT_POSITION_PRECEDING || ziel.contains(stuecke[i])) aufdecken(stuecke[i], true);
    }
  }
  if (!ruhig && 'IntersectionObserver' in window) {
    var hoehe = window.innerHeight;
    var kandidaten = document.querySelectorAll(LESESTUECKE);
    for (var k = 0; k < kandidaten.length; k++) {
      if (kandidaten[k].getBoundingClientRect().top > hoehe * 0.92) kandidaten[k].classList.add('vorher');
    }
    lesen = new IntersectionObserver(function (eintraege) {
      var rein = [];
      eintraege.forEach(function (e) {
        if (e.isIntersecting) rein.push(e.target);
        else if (e.boundingClientRect.bottom < 0) aufdecken(e.target, true);
      });
      rein.sort(function (a, b) { return a.getBoundingClientRect().top - b.getBoundingClientRect().top; });
      rein.forEach(function (el, i) {
        el.style.setProperty('--verzug', (i < 5 ? i * 70 : 0) + 'ms');
        aufdecken(el, false);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0 });
    var verdeckt = document.querySelectorAll('.vorher');
    for (var v = 0; v < verdeckt.length; v++) lesen.observe(verdeckt[v]);
  } else {
    var alle = document.querySelectorAll('.szene-text .zahl-wert');
    for (var a = 0; a < alle.length; a++) alle[a].setAttribute('data-gezaehlt', '1');
  }
  function sprungZiel() {
    if (!location.hash || location.hash.length < 2) return;
    var ziel = null;
    try { ziel = document.querySelector(location.hash); } catch (e) { ziel = null; }
    if (ziel) alleBis(ziel);
  }
  sprungZiel();
  window.addEventListener('hashchange', sprungZiel);

  /* DIE SZENEN: am Rand steht das Kapitel, in dem der Leser gerade ist. */
  var szenen = document.querySelectorAll('.szene');
  if (szenen.length && 'IntersectionObserver' in window) {
    var marke = document.querySelector('.kapitel-marke');
    if (marke) {
      var name = marke.querySelector('[data-kapitel-name]');
      var knopf = marke.querySelector('.kapitel-aktuell');
      var verweise = marke.querySelectorAll('.kapitel-liste a');
      var kapitel = new IntersectionObserver(function (eintraege) {
        eintraege.forEach(function (e) {
          if (!e.isIntersecting) return;
          name.textContent = e.target.getAttribute('data-szene');
          for (var i = 0; i < verweise.length; i++) {
            verweise[i].classList.toggle('on', verweise[i].getAttribute('href') === '#' + e.target.id);
          }
        });
      }, { rootMargin: '-45% 0px -55% 0px' });
      for (var m = 0; m < szenen.length; m++) if (szenen[m].id) kapitel.observe(szenen[m]);
      var bericht = document.getElementById('der-wochenbericht');
      if (bericht) {
        new IntersectionObserver(function (e) {
          marke.classList.toggle('sichtbar', e[0].isIntersecting && e[0].intersectionRect.height > 0);
        }, { rootMargin: '-60% 0px 0px 0px' }).observe(bericht);
      }
      knopf.addEventListener('click', function () {
        var offen = marke.classList.toggle('offen');
        knopf.setAttribute('aria-expanded', offen ? 'true' : 'false');
      });
      for (var w = 0; w < verweise.length; w++) (function (a) {
        a.addEventListener('click', function (ev) {
          var ziel = document.querySelector(a.getAttribute('href'));
          if (!ziel) return;
          ev.preventDefault();
          alleBis(ziel);
          ziel.scrollIntoView({ behavior: 'instant', block: 'start' });
          if (history.replaceState) history.replaceState(null, '', a.getAttribute('href'));
          marke.classList.remove('offen');
          knopf.setAttribute('aria-expanded', 'false');
        });
      })(verweise[w]);
    }
  }
})();


/* MELDUNGEN (Magazin 10.10.2026): Leseansicht, Schwerpunkt, Scrollfortschritt. */
(function () {
  var panel = document.getElementById('lesepanel');
  if (!panel) return;
  var inhalt = panel.querySelector('.lesepanel-inhalt');
  var zuletzt = null;
  var ruhig = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);

  function oeffne(meldung, alsVerlauf) {
    var vorlage = meldung.querySelector('.mw-detail');
    if (!vorlage) return false;
    inhalt.innerHTML = '';
    var kopie = vorlage.cloneNode(true);
    while (kopie.firstChild) inhalt.appendChild(kopie.firstChild);
    var titel = inhalt.querySelector('.lp-titel');
    if (titel) titel.id = 'lesepanel-titel';
    zuletzt = document.activeElement;
    panel.hidden = false;
    document.documentElement.classList.add('panel-offen');
    requestAnimationFrame(function () { requestAnimationFrame(function () { panel.classList.add('offen'); }); });
    panel.querySelector('.lesepanel-blatt').scrollTop = 0;
    var zu = panel.querySelector('.lesepanel-zu');
    if (zu) zu.focus({ preventScroll: true });
    if (alsVerlauf !== false && history.replaceState) history.replaceState(null, '', '#' + meldung.id);
    return true;
  }
  function schliesse() {
    if (panel.hidden) return;
    panel.classList.remove('offen');
    document.documentElement.classList.remove('panel-offen');
    var weg = function () { panel.hidden = true; inhalt.innerHTML = ''; };
    if (ruhig) weg(); else setTimeout(weg, 320);
    if (history.replaceState) history.replaceState(null, '', location.pathname + location.search);
    if (zuletzt && zuletzt.focus) zuletzt.focus({ preventScroll: true });
  }
  document.addEventListener('click', function (ev) {
    var link = ev.target.closest && ev.target.closest('a[data-panel]');
    if (link && !ev.metaKey && !ev.ctrlKey && !ev.shiftKey) {
      var meldung = link.closest('.meldung');
      if (meldung && oeffne(meldung)) ev.preventDefault();
      return;
    }
    if (ev.target.closest && ev.target.closest('[data-schliessen]')) schliesse();
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') schliesse();
  });
  if (location.hash && /^#m-[0-9a-f]+$/.test(location.hash)) {
    var ziel = document.getElementById(location.hash.slice(1));
    if (ziel) {
      ziel.scrollIntoView({ block: 'center' });
      oeffne(ziel, false);
    }
  }

  /* Schwerpunkt: ein Verweis oeffnet die Meldung, die weiter oben oder
     unten vollstaendig steht; die Knoepfe wechseln Thema und Farbe. */
  document.addEventListener('click', function (ev) {
    var verweis = ev.target.closest && ev.target.closest('a[data-zu]');
    if (!verweis || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
    var meldung = document.getElementById(verweis.getAttribute('data-zu'));
    if (meldung && oeffne(meldung)) ev.preventDefault();
  });
  var schwerpunkt = document.querySelector('[data-schwerpunkt]');
  if (schwerpunkt) {
    var knoepfe = schwerpunkt.querySelectorAll('.mg-sp-themen [data-thema]');
    var tafeln = schwerpunkt.querySelectorAll('.mg-sp-tafel');
    for (var k = 0; k < knoepfe.length; k++) (function (b) {
      b.addEventListener('click', function () {
        var thema = b.getAttribute('data-thema');
        for (var j = 0; j < knoepfe.length; j++) knoepfe[j].setAttribute('aria-pressed', knoepfe[j] === b ? 'true' : 'false');
        for (var t = 0; t < tafeln.length; t++) {
          var an = tafeln[t].getAttribute('data-thema') === thema;
          tafeln[t].hidden = !an;
          tafeln[t].classList.toggle('neu', an && !ruhig);
        }
        schwerpunkt.className = schwerpunkt.className.replace(/\bsp--\S+/, 'sp--' + thema);
      });
    })(knoepfe[k]);
  }

  /* Weitere Meldungen: ab der achtzehnten zugeklappt, ein Knopf zeigt alle. */
  var strom = document.getElementById('mg-strom');
  var mehr = document.getElementById('mg-mehr');
  if (strom && mehr) {
    strom.classList.add('zu');
    mehr.hidden = false;
    mehr.addEventListener('click', function () { strom.classList.remove('zu'); mehr.hidden = true; });
  }

  /* Scrollfortschritt: der Titel wird kleiner, Bilder ziehen leicht mit,
     der Schwerpunkt waechst auf volle Breite, Deutschland faerbt sich ein. */
  if (ruhig) return;
  var kopf = document.querySelector('.mg-kopf:not(.wa-text)');
  var aufmacher = document.querySelector('.mg--aufmacher');
  var deutschland = document.querySelector('.mg-deutschland');
  var bewegt = [kopf, aufmacher, schwerpunkt, deutschland].filter(Boolean);
  if (!bewegt.length) return;
  var geplant = false;
  function fortschritt() {
    geplant = false;
    var vh = window.innerHeight;
    for (var i = 0; i < bewegt.length; i++) {
      var el = bewegt[i];
      var r = el.getBoundingClientRect();
      if (r.bottom < -vh || r.top > vh * 2) continue;
      var p = el === kopf ? -r.top / Math.max(1, r.height) : (vh - r.top) / (vh + r.height);
      el.style.setProperty('--p', Math.min(1, Math.max(0, p)).toFixed(4));
      if (el === schwerpunkt) {
        el.style.setProperty('--rest', Math.min(1, Math.max(0, (r.top - vh * 0.3) / (vh * 0.55))).toFixed(4));
        if (r.top < vh * 0.7) el.classList.add('da');
      }
    }
  }
  window.addEventListener('scroll', function () {
    if (!geplant) { geplant = true; requestAnimationFrame(fortschritt); }
  }, { passive: true });
  window.addEventListener('resize', fortschritt);
  fortschritt();
})();

/* WETTBEWERB WELT und PROMO (Redesign 09.10.2026): Hebel oeffnen, Marken filtern. */
(function () {
  var welt = document.querySelector('[data-welt]');
  if (welt) {
    var zeilen = welt.querySelectorAll('.wl-zeile');
    var bilder = welt.querySelectorAll('.wl-bild');
    var stapel = welt.querySelectorAll('.wl-stapel');
    var bild = function (key) {
      for (var i = 0; i < bilder.length; i++) bilder[i].classList.toggle('an', bilder[i].getAttribute('data-hebel') === key);
    };
    var stand = function (s) {
      var k = s.querySelector('.wl-karten'), anz = s.querySelector('[data-stand]');
      var karten = k ? k.querySelectorAll('.dzk') : [];
      if (!k || !anz || !karten.length) return;
      var breite = karten[0].getBoundingClientRect().width + 14;
      var n = Math.min(karten.length, Math.round(k.scrollLeft / breite) + 1);
      anz.textContent = n + ' / ' + karten.length;
    };
    var oeffne = function (key) {
      var ziel = key ? document.getElementById('dz-theme-' + key) : null;
      for (var i = 0; i < stapel.length; i++) stapel[i].classList.toggle('aktiv', stapel[i] === ziel);
      for (var z = 0; z < zeilen.length; z++) zeilen[z].classList.toggle('on', !!ziel && zeilen[z].getAttribute('data-hebel') === key);
      welt.classList.toggle('offen', !!ziel);
      document.documentElement.classList.toggle('wl-blatt-offen', !!ziel && innerWidth <= 900);
      if (!ziel) return;
      bild(key);
      var karten = ziel.querySelectorAll('.wl-karten .dzk');
      for (var c = 0; c < karten.length; c++) karten[c].style.setProperty('--n', Math.min(c, 5));
      var reihe = ziel.querySelector('.wl-karten');
      if (reihe) reihe.scrollLeft = 0;
      stand(ziel);
      var fenster = welt.querySelector('.wl-fenster');
      var oben = fenster ? fenster.getBoundingClientRect().top : 0;
      if (innerWidth > 900 && oben > 110) window.scrollBy({ top: oben - 96, behavior: 'smooth' });
    };
    var offenerKey = function () {
      for (var i = 0; i < stapel.length; i++) if (stapel[i].classList.contains('aktiv')) return stapel[i].id.slice(9);
      return '';
    };
    for (var i = 0; i < zeilen.length; i++) (function (a) {
      var key = a.getAttribute('data-hebel');
      a.addEventListener('mouseenter', function () { if (!offenerKey()) bild(key); });
      a.addEventListener('focus', function () { if (!offenerKey()) bild(key); });
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        if (history.replaceState) history.replaceState(null, '', '#dz-theme-' + key);
        oeffne(key);
      });
    })(zeilen[i]);
    for (var s = 0; s < stapel.length; s++) (function (st) {
      var reihe = st.querySelector('.wl-karten');
      var leiste = st.querySelector('.wl-blaettern');
      if (leiste) leiste.hidden = false;
      var zu = st.querySelector('.hebel-zurueck');
      if (zu) zu.addEventListener('click', function (ev) {
        ev.preventDefault();
        if (history.replaceState) history.replaceState(null, '', location.pathname + location.search);
        oeffne('');
      });
      if (reihe) reihe.addEventListener('scroll', function () { stand(st); }, { passive: true });
      var knoepfe = st.querySelectorAll('[data-schritt]');
      for (var b = 0; b < knoepfe.length; b++) (function (kn) {
        kn.addEventListener('click', function () {
          var karte = reihe && reihe.querySelector('.dzk');
          if (karte) reihe.scrollBy({ left: (karte.getBoundingClientRect().width + 14) * parseInt(kn.getAttribute('data-schritt'), 10), behavior: 'smooth' });
        });
      })(knoepfe[b]);
    })(stapel[s]);
    document.addEventListener('keydown', function (ev) {
      var key = offenerKey();
      if (!key) return;
      if (ev.key === 'Escape') { oeffne(''); return; }
      if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
        var b = document.querySelector('#dz-theme-' + key + ' [data-schritt="' + (ev.key === 'ArrowRight' ? 1 : -1) + '"]');
        if (b) { ev.preventDefault(); b.click(); }
      }
    });
    var m = /^#dz-theme-(.+)$/.exec(location.hash || '');
    if (m && document.getElementById('dz-theme-' + m[1])) {
      oeffne(m[1]);
      setTimeout(function () { welt.scrollIntoView({ block: 'start' }); }, 0);
    }
  }

  var filter = document.querySelectorAll('[data-tier-filter]');
  if (filter.length) {
    for (var f = 0; f < filter.length; f++) (function (b) {
      b.addEventListener('click', function () {
        var tier = b.getAttribute('data-tier-filter');
        for (var j = 0; j < filter.length; j++) {
          filter[j].classList.toggle('on', filter[j] === b);
          filter[j].setAttribute('aria-pressed', filter[j] === b ? 'true' : 'false');
        }
        var lauf = function () {
          var marken = document.querySelectorAll('.pmarke[data-tier]:not(.pmarke--eigen)');
          for (var m = 0; m < marken.length; m++) marken[m].hidden = !!tier && marken[m].getAttribute('data-tier') !== tier;
        };
        if (document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) document.startViewTransition(lauf);
        else lauf();
      });
    })(filter[f]);
  }
})();

/* QUELLEN (10.10.2026): der Lauf als Filter. Der Scrollfortschritt waehlt
   die Stufe; Zahl, Titel und Satz kommen aus der Stufe selbst. */
(function () {
  var f = document.querySelector('[data-filter]');
  if (!f) return;
  var lis = [].slice.call(f.querySelectorAll('.qf-leiter li'));
  var zahl = f.querySelector('[data-filter-zahl]');
  var titel = f.querySelector('[data-filter-titel]');
  var satz = f.querySelector('[data-filter-satz]');
  var leiter = f.querySelector('.qf-leiter');
  if (!lis.length || !zahl) return;
  var ruhig = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var akt = -1, anim = 0, ANTEIL = 0.86;
  function fmt(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
  function wert(i) { return parseInt(lis[i].getAttribute('data-zahl'), 10) || 0; }
  function zaehle(von, i) {
    var bis = wert(i), ende = lis[i].querySelector('b').textContent;
    cancelAnimationFrame(anim);
    if (ruhig) { zahl.textContent = ende; return; }
    var t0 = null;
    function s(t) {
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3);
      zahl.textContent = k < 1 ? fmt(Math.round(von + (bis - von) * e)) : ende;
      if (k < 1) anim = requestAnimationFrame(s);
    }
    anim = requestAnimationFrame(s);
  }
  function stufe(i) {
    if (i === akt) return;
    var alt = akt; akt = i;
    lis.forEach(function (l, j) { l.classList.toggle('erreicht', j <= i); l.classList.toggle('jetzt', j === i); });
    leiter.style.setProperty('--fort', (lis.length > 1 ? i / (lis.length - 1) : 1).toFixed(3));
    titel.textContent = lis[i].querySelector('span').textContent;
    satz.textContent = lis[i].getAttribute('data-satz');
    zaehle(alt < 0 ? wert(i) : wert(alt), i);
  }
  var geplant = false;
  function rechnen() {
    geplant = false;
    var r = f.getBoundingClientRect(), weg = Math.max(1, r.height - window.innerHeight);
    var p = Math.min(1, Math.max(0, -r.top / weg));
    var q = Math.max(0, (p - ANTEIL) / (1 - ANTEIL));
    f.style.setProperty('--p', Math.min(1, p / ANTEIL).toFixed(3));
    f.style.setProperty('--q', q.toFixed(3));
    stufe(Math.min(lis.length - 1, Math.floor(Math.min(0.999, p / ANTEIL) * lis.length)));
  }
  window.addEventListener('scroll', function () {
    if (!geplant) { geplant = true; requestAnimationFrame(rechnen); }
  }, { passive: true });
  window.addEventListener('resize', rechnen);
  lis.forEach(function (l, j) {
    l.addEventListener('click', function () {
      var weg = f.offsetHeight - window.innerHeight;
      window.scrollTo({ top: f.offsetTop + weg * ANTEIL * (j + 0.5) / lis.length, behavior: ruhig ? 'auto' : 'smooth' });
    });
  });
  rechnen();
})();

/* KINOSTRECKE (Wettbewerb, 10.10.2026): Buehnen mit data-buehne bekommen
   ihren Scrollfortschritt als --p; der Puls zeichnet sich, wenn er ins Bild
   kommt; Zahlen mit data-zaehler zaehlen bis zu ihrem eigenen Text hoch. */
(function () {
  var buehnen = document.querySelectorAll('[data-buehne]');
  var puls = document.querySelectorAll('[data-puls]');
  if (!buehnen.length && !puls.length) return;
  var ruhig = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var ziele = [];
  for (var i = 0; i < buehnen.length; i++) ziele.push(buehnen[i].closest('.wa-kapitel') || buehnen[i]);
  var geplant = false;
  function rechnen() {
    geplant = false;
    var h = window.innerHeight;
    ziele.forEach(function (s) {
      var r = s.getBoundingClientRect();
      if (r.bottom < -h || r.top > h * 2) return;
      var weg = s.classList.contains('wa-kapitel') ? h * 0.9 : Math.max(1, r.height - h);
      s.style.setProperty('--p', Math.min(1, Math.max(0, -r.top / weg)).toFixed(3));
    });
  }
  if (!ruhig && ziele.length) {
    window.addEventListener('scroll', function () {
      if (!geplant) { geplant = true; requestAnimationFrame(rechnen); }
    }, { passive: true });
    window.addEventListener('resize', rechnen);
    rechnen();
  }
  function zaehlen(el) {
    var ziel = el.textContent, n = parseInt(ziel, 10), t0 = null;
    if (ruhig || !n) return;
    function schritt(t) {
      if (!t0) t0 = t;
      var k = Math.min(1, (t - t0) / 1100);
      el.textContent = k < 1 ? String(Math.round(n * (1 - Math.pow(1 - k, 3)))) : ziel;
      if (k < 1) requestAnimationFrame(schritt);
    }
    requestAnimationFrame(schritt);
  }
  var pause = document.querySelector('[data-wand-pause]');
  if (pause) pause.addEventListener('click', function () {
    var an = pause.parentNode.classList.toggle('angehalten');
    pause.setAttribute('aria-pressed', an ? 'true' : 'false');
    pause.textContent = an ? 'Weiterlaufen' : 'Anhalten';
  });
  var beobachtet = document.querySelectorAll('[data-puls],[data-zaehler],[data-buchstaben]');
  if (!('IntersectionObserver' in window)) {
    for (var j = 0; j < beobachtet.length; j++) beobachtet[j].classList.add('sichtbar');
    return;
  }
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add('sichtbar');
      if (e.target.hasAttribute('data-zaehler')) zaehlen(e.target);
      io.unobserve(e.target);
    });
  }, { threshold: 0.18 });
  for (var k = 0; k < beobachtet.length; k++) io.observe(beobachtet[k]);
})();

/* DIE ANKUNFTS-ADRESSE, EINMAL GESICHERT (P2, 17.09.2026). Die Zeitreihen-
   Steuerung des Vergleichs-Reiters schreibt beim Laden ihren Startzustand
   per history.replaceState in die URL ("?modell=...&band=...") - auch wenn
   der Leser gar keinen Parameter mitbrachte. Wer die Adresse DANACH liest,
   haelt interne Zustandsspeicherung fuer einen Leser-Wunsch: die Auto-
   Vorauswahl des Preisverlaufs wuerde so immer das Vorgabemodell der
   Zeitreihe zeigen statt des meistgemessenen Geraets. Die eine Zeile hier
   friert die Suchzeichenfolge der ANKUNFT ein; fuer Leser-Wuensche gilt
   nur sie. */
var TR_ANKUNFT_SEARCH = location.search;
/* DAS GERAET DES LESERS (28.09.2026): „Mit Tarif“ und „Ohne Vertrag“ zeigen
   dasselbe Geraet. Gemeinsam ist nur, was ein LESER wollte - ein
   ?modell=-Deep-Link bei Ankunft oder eine Wahl in einem der beiden
   Reiter. Das ?modell=, das „Mit Tarif“ beim Laden fuer sein Startgeraet
   in die Adresse schreibt, ist interne Zustandsspeicherung und gilt
   hier NICHT (sonst ueberschriebe es einen Deep-Link auf ein Geraet ohne
   Buendel). */
var TR_LESER_MODELL = null;
try { TR_LESER_MODELL = new URLSearchParams(TR_ANKUNFT_SEARCH).get('modell'); }
catch (e) { /* aeltere Browser: keine Uebernahme */ }

/* P2/D4b: DER AKTIVE NAVIGATIONSEINTRAG STEHT IM BILD - auf jeder Seite.
 * `.subbar.subnav` (base.html.j2) rollt seit dem 08.08.2026 seitlich statt
 * umzubrechen, mit einem weichen Rand als Scroll-Hinweis - der Rand sagt
 * "hier geht es weiter", er bringt aber die eigene Seite nicht ins Bild.
 * Gemessen auf geraete.html bei 390 px: der Eintrag "Geräte" (aktiv, class
 * "on") stand bei x=536-620, KOMPLETT ausserhalb des 390-px-Viewports -
 * ein Leser sah beim Landen weder, dass er auf "Geräte" steht, noch (weil
 * der Eintrag davor faellt) den vollstaendigen Text von "Differenzierung"
 * (bis x=410, 20 px abgeschnitten). Dieselbe Leiste blieb aber FUNKTIONAL
 * erreichbar - `overflow-x:auto` scrollt, nur ohne dass beim Laden je
 * dorthin gescrollt wurde. Diese eine Zeile holt den aktiven Eintrag beim
 * Laden mittig ins Bild, wie es ein Klick auf einen Reiter-Knopf der
 * Geräteseite ueber den nativen Fokus-Scroll ohnehin schon tut. */
(function () {
  try {
    var aktiv = document.querySelector('.subbar.subnav a.on');
    if (aktiv) aktiv.scrollIntoView({ inline: 'center', block: 'nearest' });
  } catch (e) { /* scrollIntoView mit Optionen fehlt: Leiste bleibt am
                   Anfang, aber weiterhin nutzbar (kein Crash). */ }
})();

(function () {
  'use strict';

  const dataEl = document.getElementById('explorer-data');
  if (!dataEl) return;
  let items = [];
  try { items = JSON.parse(dataEl.textContent); } catch (e) { return; }

  const listEl = document.getElementById('ex-list');
  const detailEl = document.getElementById('ex-detail');
  // Wie tief die aktuelle Seite unter site/ liegt. Die Archivwochen stehen
  // in reports/, alles andere direkt darunter.
  function uebPrefix() {
    return location.pathname.indexOf('/reports/') !== -1 ? '../' : '';
  }
  const countEl = document.getElementById('ex-count');
  const fSearch = document.getElementById('f-search');
  const fRegion = document.getElementById('f-region');
  const fCategory = document.getElementById('f-category');
  const fRelevance = document.getElementById('f-relevance');
  const fSort = document.getElementById('f-sort');
  if (!listEl) return;

  const REL_LABEL = { 5: 'Sofort ansehen', 4: 'Wichtig', 3: 'Beobachten', 2: 'Randnotiz', 1: 'Randnotiz', 0: 'Unbewertet' };
  let visible = [];
  let selectedId = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function relClass(r) { return 'r' + (r >= 2 ? r : 0); }

  function matches(h) {
    const q = (fSearch.value || '').trim().toLowerCase();
    if (q) {
      const hay = ((h.operator || '') + ' ' + (h.title || '') + ' ' + (h.summary || '') + ' ' + (h.source_label || '')).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (fRegion.value && h.region !== fRegion.value) return false;
    if (fCategory.value && h.category !== fCategory.value) return false;
    const minRel = parseInt(fRelevance.value || '0', 10);
    if (minRel && (h.relevance || 0) < minRel) return false;
    return true;
  }

  function sortItems(arr) {
    const mode = fSort.value;
    const copy = arr.slice();
    if (mode === 'date') {
      copy.sort(function (a, b) { return (b.date || '').localeCompare(a.date || '') || b.relevance - a.relevance; });
    } else if (mode === 'operator') {
      copy.sort(function (a, b) { return (a.operator || 'zz').localeCompare(b.operator || 'zz') || b.relevance - a.relevance; });
    } else {
      copy.sort(function (a, b) { return b.relevance - a.relevance || (b.date || '').localeCompare(a.date || ''); });
    }
    return copy;
  }

  function renderList() {
    visible = sortItems(items.filter(matches));
    listEl.innerHTML = visible.map(function (h) {
      return '<div class="ex-row' + (h.id === selectedId ? ' active' : '') + '" data-id="' + h.id + '" role="option" tabindex="0">' +
        '<div class="ex-row-top">' +
          '<span class="ex-dot ' + relClass(h.relevance) + '"></span>' +
          '<span class="ex-op">' + esc(h.operator || h.source_label || '–') + '</span>' +
          '<span class="ex-reg">' + esc(h.region) + (h.date ? ' · ' + esc(h.date) : '') + '</span>' +
        '</div>' +
        '<div class="ex-title">' + esc(h.title) + '</div>' +
      '</div>';
    }).join('');
    countEl.textContent = visible.length + ' von ' + items.length + ' Meldungen' +
      (visible.length < items.length ? ' (gefiltert)' : '');
    if (visible.length && (selectedId === null || !visible.some(function (h) { return h.id === selectedId; }))) {
      select(visible[0].id, false);
    } else if (!visible.length) {
      detailEl.innerHTML = '<p class="ex-detail-empty">Keine Meldung passt zu diesen Filtern.</p>';
    }
  }

  function select(id, scroll) {
    selectedId = id;
    const h = items.find(function (x) { return x.id === id; });
    if (!h) return;
    listEl.querySelectorAll('.ex-row').forEach(function (row) {
      row.classList.toggle('active', parseInt(row.dataset.id, 10) === id);
    });
    const relTxt = h.relevance >= 2 ? h.relevance + '/5 · ' + (REL_LABEL[h.relevance] || '') : 'Unbewertet';
    detailEl.innerHTML =
      '<div class="ex-d-top">' +
        '<span class="rel-badge ' + relClass(h.relevance) + '">' + esc(relTxt) + '</span>' +
        '<span class="chip">' + esc(h.category) + '</span>' +
        '<span class="chip">' + esc(h.region) + '</span>' +
      '</div>' +
      '<h3><a href="' + esc(h.url) + '" target="_blank" rel="noopener">' + esc(h.title) + '</a></h3>' +
      '<p class="ex-d-meta"><b>' + esc(h.operator || '–') + '</b>' +
        (h.date ? ' · ' + esc(h.date) : '') +
        (h.source_label ? ' · Quelle: ' + esc(h.source_label) : '') + '</p>' +
      (h.summary ? '<p class="ex-d-sum">' + esc(h.summary) + '</p>' : '') +
      '<a class="source-link" href="' + esc(h.url) + '" target="_blank" rel="noopener">Originalquelle öffnen (' + esc(h.source_label || 'Link') + ') &nearr;</a>' +
      // Der rote Link zur vollstaendigen Uebersetzung, wenn es eine gibt.
      // Er steht NACH der Originalquelle, nicht an ihrer Stelle: das
      // Original bleibt der Beleg, die Uebersetzung ist das Angebot.
      // `prefix` traegt die Seite als data-Attribut - der Explorer steht
      // auf meldungen.html (prefix "") und unter reports/<datum>.html
      // (prefix "../"), und ein fester Pfad waere an einem der beiden Orte
      // falsch.
      // Die Beschriftung steht WOERTLICH so auch in _uebersetzung.html.j2.
      // Zwei Umsetzungen derselben Sache laufen auseinander - deshalb haelt
      // test_die_beschriftung_ist_an_beiden_orten_dieselbe sie zusammen.
      (h.uebersetzung
        ? '<p class="ueb-link"><a href="' + esc(uebPrefix()) + esc(h.uebersetzung) + '">Übersetzung lesen</a></p>'
        : '');
    if (scroll && window.innerWidth <= 880) detailEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  listEl.addEventListener('click', function (e) {
    const row = e.target.closest('.ex-row');
    if (row) select(parseInt(row.dataset.id, 10), true);
  });
  listEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') {
      const row = e.target.closest('.ex-row');
      if (row) { e.preventDefault(); select(parseInt(row.dataset.id, 10), true); }
    }
  });

  let t;
  fSearch.addEventListener('input', function () { clearTimeout(t); t = setTimeout(renderList, 120); });
  [fRegion, fCategory, fRelevance, fSort].forEach(function (el) { el.addEventListener('change', renderList); });

  renderList();

  // Ankunft ueber die Dossier-Seite mit ?q=…: Suchfeld vorbelegen,
  // Explorer-Akkordeon oeffnen und sofort filtern - kein zweites Mal tippen.
  //
  // Der Explorer steht nur auf den Archivwochen unter reports/, und genau
  // dorthin verlinkt ein Dossier-Treffer ("in dieser Ausgabe ansehen"). Bis
  // zum 08.08.2026 stand hier eine Ausnahme fuer meldungen.html, weil dort
  // ein zweites Suchfeld dasselbe ?q= las; das Feld ist weg, die Suche hat
  // ihre eigene Seite.
  try {
    var qs = new URLSearchParams(location.search);
    var q = qs.get('q');
    if (q) {
      fSearch.value = q;
      renderList();
      var det = listEl.closest('details.evidence');
      if (det) { det.open = true; det.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
  } catch (e) { /* URLSearchParams nicht verfuegbar - stiller Fallback */ }
})();

/* Promo Übersicht - Wettbewerber-Board: Tier-Filter (Vanilla JS, kein Framework) */
(function () {
  'use strict';
  const board = document.getElementById('promo-board');
  if (!board) return;
  const buttons = document.querySelectorAll('.promo-filter');
  if (!buttons.length) return;

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      buttons.forEach(function (b) { b.classList.remove('on'); });
      btn.classList.add('on');
      const tier = btn.dataset.tier;
      board.querySelectorAll('.promo-card').forEach(function (card) {
        card.hidden = tier !== 'all' && card.dataset.tier !== tier;
      });
    });
  });
})();

/* Die Suchmaschine der Seite. Sie durchsucht `search_index.json` - die
   bewerteten Meldungen ALLER Ausgaben, die Differenzierungs-Bibliothek und die
   Promo-Aktionen (report/suchindex.py). Kein Suchserver: der Index ist ein
   JSON-Array, das der Browser einmal laedt und dann filtert.

   Am 08.08.2026 hat diese Schicht zwei Dinge dazubekommen, und beide gehen auf
   denselben Satz zurueck ("wenn ich suche, alle Meldungen super dargestellt,
   dass ich einen Ueberblick habe"):

   1. WORTWEISES SUCHEN STATT EINER ZEICHENKETTE. Vorher musste die Eingabe
      als Ganzes im Text vorkommen; "telekom perplexity" fand nichts, obwohl
      genau diese Kombination der Anlass der Suche war. Jetzt muss JEDES Wort
      vorkommen (UND-Verknuepfung), irgendwo im Eintrag.
   2. EINE RANGFOLGE. Vorher war jeder Treffer gleich viel wert und die Liste
      stand in Indexreihenfolge. Ein Treffer im Absender wiegt jetzt schwerer
      als einer im Fliesstext, und die Dringlichkeit der Meldung geht mit ein -
      sonst fuehrt eine Randnotiz das Dossier an. */
var TelcoSearch = (function () {
  'use strict';

  var KIND_LABEL = { bericht: 'Meldung', differenzierung: 'Differenzierung',
                     promo: 'Aktion' };
  var items = null;   // null = noch nicht geladen; [] = geladen, leer
  var loading = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Der Praefix (z. B. "" auf der Startseite, "../" unter reports/ oder
  // promo/) steckt schon serverseitig im Brand-Link - so muss app.js (eine
  // einzige, seitenunabhaengige Datei) ihn nicht selbst erraten.
  function prefix() {
    var brand = document.querySelector('.topbar .brand');
    var href = brand ? brand.getAttribute('href') || '' : '';
    return href.slice(0, href.length - 'index.html'.length) || '';
  }

  function loadIndex() {
    if (items !== null) return Promise.resolve(items);
    if (loading) return loading;
    loading = fetch(prefix() + 'search_index.json')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (data) { items = Array.isArray(data) ? data : []; return items; })
      .catch(function () { items = []; return items; });
    return loading;
  }

  function worte(q) {
    return String(q || '').toLowerCase().split(/\s+/).filter(function (w) {
      return w.length > 0;
    });
  }

  function felder(it) {
    return {
      op: String(it.operator || '').toLowerCase(),
      titel: String(it.title || '').toLowerCase(),
      rest: [it.summary, it.region, it.category, it.source_label]
        .filter(Boolean).join(' — ').toLowerCase()
    };
  }

  /* 0 = kein Treffer. Sonst: je Wort das schwerste Feld, in dem es steht,
     plus die Dringlichkeit der Meldung als Stichentscheid. */
  function score(it, ws) {
    if (!ws.length) return 0;
    var f = felder(it);
    var summe = 0;
    for (var i = 0; i < ws.length; i++) {
      var w = ws[i];
      if (f.op.indexOf(w) !== -1) summe += 8;
      else if (f.titel.indexOf(w) !== -1) summe += 5;
      else if (f.rest.indexOf(w) !== -1) summe += 2;
      else return 0;             // UND-Verknuepfung: ein fehlendes Wort kippt
    }
    return summe + (it.relevance || 0);
  }

  function suche(alle, q) {
    var ws = worte(q);
    if (!ws.length) return [];
    var out = [];
    for (var i = 0; i < alle.length; i++) {
      var s = score(alle[i], ws);
      if (s) out.push({ it: alle[i], score: s });
    }
    return out;
  }

  /* Der Suchbegriff im Text hervorgehoben. Der Text selbst wird NICHT
     gekuerzt - eine Schlagzeile mit "…" am Ende ist ein abgeschnittener Satz,
     und die verbietet diese Codebasis ueberall sonst (CLAUDE.md §5,
     Abnahmekriterium 5). Gekuerzt wird nur der Fliesstext, und dort auch nur
     am Ende. */
  function markiere(text, ws) {
    var roh = String(text || '');
    if (!ws.length) return esc(roh);
    var lower = roh.toLowerCase();
    var stellen = [];
    for (var i = 0; i < ws.length; i++) {
      var von = lower.indexOf(ws[i]);
      while (von !== -1) {
        stellen.push([von, von + ws[i].length]);
        von = lower.indexOf(ws[i], von + ws[i].length);
      }
    }
    if (!stellen.length) return esc(roh);
    stellen.sort(function (a, b) { return a[0] - b[0]; });
    var out = '';
    var pos = 0;
    for (var j = 0; j < stellen.length; j++) {
      if (stellen[j][0] < pos) continue;
      out += esc(roh.slice(pos, stellen[j][0])) +
        '<mark>' + esc(roh.slice(stellen[j][0], stellen[j][1])) + '</mark>';
      pos = stellen[j][1];
    }
    return out + esc(roh.slice(pos));
  }

  // Deep-Link zum vollen Kontext: Meldungen haengen ?q= an, damit der
  // Explorer der jeweiligen Ausgabe sofort gefiltert oeffnet (siehe die
  // Explorer-IIFE weiter oben in dieser Datei); Differenzierung und Aktionen
  // springen direkt zu ihrem Abschnitt - dort gibt es keinen Begriffsfilter.
  function deepLinkHref(it, q) {
    var p = prefix();
    if (it.kind === 'bericht' && q) {
      return p + it.deep_link + '?q=' + encodeURIComponent(q);
    }
    return p + it.deep_link;
  }

  return {
    KIND_LABEL: KIND_LABEL, esc: esc, prefix: prefix, loadIndex: loadIndex,
    worte: worte, score: score, suche: suche, markiere: markiere,
    deepLinkHref: deepLinkHref
  };
})();

/* Die Dossier-Seite (suche.html).

   Sie beantwortet nicht "welche Zeilen enthalten mein Wort", sondern "was
   weiss dieses Portal ueber mein Thema, und wie hat es sich entwickelt".
   Daraus folgt der Aufbau, und zwar in dieser Reihenfolge:

     BILANZ     wie viele Treffer, ueber welchen Zeitraum, aus wie vielen
                Quellen - drei Zahlen, die den Rest einordnen.
     UEBERBLICK Verlauf ueber die Monate, haeufigste Absender, haeufigste
                Ressorts. Das ist die "Entwicklung", nach der Antonio gefragt
                hat, und sie steht VOR der ersten Meldung.
     AUFMACHER  der staerkste Treffer, gross und mit Bild.
     CHRONIK    alle uebrigen nach Monaten, neueste zuerst, mit Bildern -
                die Historie in der Reihenfolge, in der sie passiert ist.

   Alles ausser dem Suchfeld wird hier gebaut; die Vorlage liefert nur die
   Behaelter (templates/suche.html.j2). */
(function () {
  'use strict';
  var input = document.getElementById('dossier-input');
  var trefferEl = document.getElementById('dossier-treffer');
  if (!input || !trefferEl) return;

  var startEl = document.getElementById('dossier-start');
  var titelEl = document.getElementById('dossier-titel');
  var bilanzEl = document.getElementById('dossier-bilanz');
  var analyseEl = document.getElementById('dossier-analyse');
  var filterEl = document.getElementById('dossier-filter');
  var verlaufEl = document.getElementById('dossier-verlauf');
  var werEl = document.getElementById('dossier-wer');
  var worumEl = document.getElementById('dossier-worum');
  var form = document.getElementById('dossier-form');

  var MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
                'August', 'September', 'Oktober', 'November', 'Dezember'];
  // Wie viele Treffer als Bildkarte stehen, bevor der Rest zur Zeile wird.
  // Sechs fuellen zwei Reihen zu dritt; darueber hinaus waere die Chronik
  // wieder eine Kachelwand, und lesbar ist eine Zeile ohnehin schneller.
  var KARTEN_JE_MONAT = 6;
  var bereich = 'all';
  var t;

  var esc = TelcoSearch.esc;

  function datumDe(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    if (!m) return '';
    return parseInt(m[3], 10) + '. ' + MONATE[parseInt(m[2], 10) - 1] + ' ' + m[1];
  }

  function monatDe(schluessel) {
    var m = /^(\d{4})-(\d{2})/.exec(schluessel || '');
    return m ? MONATE[parseInt(m[2], 10) - 1] + ' ' + m[1] : 'Ohne Datum';
  }

  function zaehle(liste, feld) {
    var z = {};
    liste.forEach(function (it) {
      var wert = (it[feld] || '').trim();
      if (wert) z[wert] = (z[wert] || 0) + 1;
    });
    return z;
  }

  /* Gezaehlte Werte als Balken. Dieselbe Bauform wie das Marktbild der
     Differenzierungs-Seite - eine Zahlenreihe, ein Aussehen. */
  function balken(el, zaehler, grenze, reihenfolge) {
    var paare = Object.keys(zaehler).map(function (k) {
      return { name: k, n: zaehler[k] };
    });
    if (reihenfolge === 'name') paare.sort(function (a, b) { return a.name < b.name ? -1 : 1; });
    else paare.sort(function (a, b) { return b.n - a.n || (a.name < b.name ? -1 : 1); });
    if (grenze) paare = paare.slice(0, grenze);
    var hoechste = paare.reduce(function (m, p) { return Math.max(m, p.n); }, 0);
    el.innerHTML = paare.map(function (p) {
      var w = hoechste ? Math.round(100 * p.n / hoechste) : 0;
      return '<li><span class="dz-balken-name">' + esc(p.name) + '</span>' +
        '<span class="dz-balken-spur"><span class="dz-balken-fuell" style="width:' + w + '%"></span></span>' +
        '<span class="dz-balken-n">' + p.n + '</span></li>';
    }).join('');
  }

  function motiv(it) {
    if (it.image) {
      return '<span class="dsk-motiv"><img src="' + esc(TelcoSearch.prefix() + it.image) +
        '" alt=""' + (it.image_w ? ' width="' + it.image_w + '" height="' + it.image_h + '"' : '') +
        ' loading="lazy"></span>';
    }
    // Kein belegtes Bild: die Schriftkachel mit dem Absender. Dieselbe Regel
    // wie auf der Promo-Uebersicht und der Differenzierung - jede Karte
    // traegt ein Motiv, nie einen leeren Kasten.
    return '<span class="dsk-motiv"><span class="dsk-kachel">' +
      esc(it.operator || it.source_label || 'Meldung') + '</span></span>';
  }

  function meta(it, ohneAbsender) {
    var teile = [ohneAbsender ? '' : it.operator, it.region, datumDe(it.date)]
      .filter(Boolean);
    return teile.join(' · ');
  }

  function kontextLabel(it) {
    if (it.kind === 'bericht') return 'In der Ausgabe ansehen';
    if (it.kind === 'promo') return 'Auf der Promo Übersicht ansehen';
    return 'Im Differenzierungs-Hebel ansehen';
  }

  function karte(it, ws, q, stufe) {
    var zeile = stufe === 'zeile';
    var klasse = 'dsk' + (stufe ? ' dsk--' + stufe : '') +
      (it.image ? '' : ' ohne-bild');
    // Traegt die Schriftkachel schon den Absender, faellt er aus der
    // Metazeile - sonst steht derselbe Name zweimal untereinander.
    var ohneAbsender = !it.image && !zeile;
    return '<article class="' + klasse + '">' +
      (zeile ? '' : motiv(it)) +
      '<div class="dsk-text">' +
        '<p class="dsk-kopf">' +
          '<span class="dsk-art ' + esc(it.kind) + '">' +
            esc(TelcoSearch.KIND_LABEL[it.kind] || it.kind) + '</span>' +
          '<span class="dsk-meta">' + esc(meta(it, ohneAbsender)) + '</span>' +
          (it.status ? '<span class="dsk-status">' + esc(it.status) + '</span>' : '') +
        '</p>' +
        '<a class="dsk-titel szl" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
          TelcoSearch.markiere(it.title, ws) + '</a>' +
        (!zeile && it.summary && it.summary !== it.title
          ? '<p class="dsk-anriss">' + TelcoSearch.markiere(it.summary, ws) + '</p>' : '') +
        '<p class="dsk-fuss">' +
          '<a class="dsk-quelle" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
            esc(it.source_label || 'Quelle') + ' &nearr;</a>' +
          '<a class="dsk-kontext" href="' + esc(TelcoSearch.deepLinkHref(it, q)) + '">' +
            kontextLabel(it) + ' &rsaquo;</a>' +
        '</p>' +
      '</div>' +
    '</article>';
  }

  function chronik(treffer, ws, q) {
    // Nach Monat, neueste zuerst. Die Chronik IST die Historie - deshalb
    // sortiert sie nach Datum und nicht nach Punktzahl; die Punktzahl
    // entscheidet nur, wer den Aufmacher stellt.
    var monate = [];
    var nachMonat = {};
    treffer.forEach(function (it) {
      var key = (it.date || '').slice(0, 7) || '0000-00';
      if (!nachMonat[key]) { nachMonat[key] = []; monate.push(key); }
      nachMonat[key].push(it);
    });
    monate.sort().reverse();
    return monate.map(function (key) {
      var liste = nachMonat[key];
      var karten = liste.slice(0, KARTEN_JE_MONAT);
      var zeilen = liste.slice(KARTEN_JE_MONAT);
      return '<section class="dossier-monat">' +
        '<div class="rubrik"><h2>' + esc(monatDe(key)) + '</h2>' +
        '<span class="rubrik-zahl">' + liste.length + ' Treffer</span></div>' +
        '<div class="dossier-raster">' +
          karten.map(function (it) { return karte(it, ws, q); }).join('') +
        '</div>' +
        (zeilen.length
          ? '<div class="dossier-zeilen">' +
              zeilen.map(function (it) { return karte(it, ws, q, 'zeile'); }).join('') +
            '</div>'
          : '') +
      '</section>';
    }).join('');
  }

  function bilanz(treffer, q) {
    var mitDatum = treffer.map(function (it) { return it.date; })
      .filter(Boolean).sort();
    var quellen = {};
    treffer.forEach(function (it) { if (it.source_label) quellen[it.source_label] = 1; });
    var teile = [treffer.length + (treffer.length === 1 ? ' Treffer' : ' Treffer')];
    if (mitDatum.length > 1 && mitDatum[0] !== mitDatum[mitDatum.length - 1]) {
      teile.push('von ' + datumDe(mitDatum[0]) + ' bis ' +
                 datumDe(mitDatum[mitDatum.length - 1]));
    } else if (mitDatum.length) {
      teile.push('vom ' + datumDe(mitDatum[0]));
    }
    var n = Object.keys(quellen).length;
    if (n) teile.push(n + (n === 1 ? ' Quelle' : ' Quellen'));
    return teile.join(' · ');
  }

  function filterZeile(alle, ws) {
    // Die Zahl je Bereich steht am Filter, nicht daneben - sie ist der
    // Grund, ihn zu druecken.
    var arten = ['all', 'bericht', 'differenzierung', 'promo'];
    var zaehler = {};
    alle.forEach(function (h) { zaehler[h.it.kind] = (zaehler[h.it.kind] || 0) + 1; });
    filterEl.innerHTML = arten.filter(function (a) {
      return a === 'all' || zaehler[a];
    }).map(function (a) {
      var n = a === 'all' ? alle.length : zaehler[a];
      var label = a === 'all' ? 'Alles' : (TelcoSearch.KIND_LABEL[a] || a);
      return '<button type="button" class="suche-filter' + (a === bereich ? ' on' : '') +
        '" data-kind="' + a + '">' + esc(label) + ' <span class="suche-filter-n">' +
        n + '</span></button>';
    }).join('');
  }

  function zeichne(q) {
    var ws = TelcoSearch.worte(q);
    if (!ws.length) {
      titelEl.textContent = 'Suche im Archiv';
      bilanzEl.textContent = '';
      trefferEl.innerHTML = '';
      analyseEl.hidden = true;
      filterEl.hidden = true;
      if (startEl) startEl.hidden = false;
      document.title = 'Marktrecherche · Suche';
      return;
    }
    if (startEl) startEl.hidden = true;
    titelEl.textContent = q;
    document.title = q + ' · Dossier';

    TelcoSearch.loadIndex().then(function (alleEintraege) {
      var alle = TelcoSearch.suche(alleEintraege, q);
      filterZeile(alle, ws);
      filterEl.hidden = !alle.length;

      var gefiltert = bereich === 'all' ? alle
        : alle.filter(function (h) { return h.it.kind === bereich; });
      var treffer = gefiltert.map(function (h) { return h.it; });

      if (!treffer.length) {
        bilanzEl.textContent = '';
        analyseEl.hidden = true;
        trefferEl.innerHTML = '<p class="empty-note">Keine Treffer für „' +
          esc(q) + '“.</p>';
        return;
      }

      bilanzEl.textContent = bilanz(treffer, q);

      analyseEl.hidden = false;
      var proMonat = {};
      treffer.forEach(function (it) {
        var key = (it.date || '').slice(0, 7);
        if (key) proMonat[monatDe(key)] = (proMonat[monatDe(key)] || 0) + 1;
      });
      balken(verlaufEl, proMonat, 12, 'name');
      balken(werEl, zaehle(treffer, 'operator'), 8);
      balken(worumEl, zaehle(treffer, 'category'), 8);

      // Der Aufmacher: der staerkste Treffer, aber unter gleich starken der
      // mit Bild - eine leere grosse Position ist genau der Zustand, den die
      // Bebilderung gerade behebt.
      var sortiert = gefiltert.slice().sort(function (a, b) {
        return b.score - a.score ||
          (b.it.date || '').localeCompare(a.it.date || '');
      });
      var spitze = sortiert[0].score;
      var kopf = sortiert.filter(function (h) { return h.score === spitze; })
        .sort(function (a, b) { return (b.it.image ? 1 : 0) - (a.it.image ? 1 : 0); })[0].it;

      var rest = treffer.filter(function (it) { return it !== kopf; })
        .sort(function (a, b) {
          return (b.date || '').localeCompare(a.date || '') ||
            (b.relevance || 0) - (a.relevance || 0);
        });

      trefferEl.innerHTML =
        '<section class="dossier-lead">' + karte(kopf, ws, q, 'lead') + '</section>' +
        chronik(rest, ws, q);
    });
  }

  function lauf() {
    var q = (input.value || '').trim();
    try {
      var url = new URL(location.href);
      if (q) url.searchParams.set('q', q); else url.searchParams.delete('q');
      history.replaceState(null, '', url.pathname + url.search + url.hash);
    } catch (e) { /* URL() nicht verfuegbar - stiller Fallback, Seite bleibt nutzbar */ }
    zeichne(q);
  }

  input.addEventListener('input', function () {
    clearTimeout(t); t = setTimeout(lauf, 150);
  });
  if (form) {
    // Ohne das laedt das Formular die Seite neu und die Eingabe verliert den
    // Fokus - der Unterschied zwischen einer Suche und einem Seitenwechsel.
    form.addEventListener('submit', function (ev) { ev.preventDefault(); lauf(); });
  }
  filterEl.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('.suche-filter') : null;
    if (!btn) return;
    bereich = btn.dataset.kind || 'all';
    zeichne((input.value || '').trim());
  });

  try {
    var q0 = new URLSearchParams(location.search).get('q');
    if (q0) input.value = q0;
  } catch (e) { /* URLSearchParams nicht verfuegbar - stiller Fallback */ }
  zeichne((input.value || '').trim());
})();

/* Meldungsseite (meldungen.html): die Ressortbloecke sind <details>.

   Der Filter, der hier bis zum 07.08.2026 stand, ist weg (Antonio: "macht
   diesen Filter weg ... das ist unnoetig") - samt der data-such-Attribute,
   die es nur fuer ihn gab. Was bleibt, ist der Weg von der Uebersichtskachel
   in die Tiefe: EINE Geste, nicht drei.

   Ohne dieses Skript funktioniert die Seite weiterhin - <details> klappt
   auch per Klick auf die Rubrikzeile auf. Das Skript erspart nur den
   zweiten Klick nach dem Sprung. */
(function () {
  'use strict';
  var tiefe = document.querySelector('.ressort-tiefe');
  if (!tiefe) return;

  function oeffne(id, scrollen) {
    var el = document.getElementById(id);
    if (!el || el.tagName.toLowerCase() !== 'details') return false;
    el.open = true;
    if (scrollen) {
      // Erst nach dem Aufklappen scrollen, sonst zielt der Browser auf die
      // Position von vorher.
      requestAnimationFrame(function () {
        el.scrollIntoView({ block: 'start', behavior: 'smooth' });
      });
    }
    return true;
  }

  document.addEventListener('click', function (ev) {
    var a = ev.target.closest ? ev.target.closest('[data-oeffnet]') : null;
    if (!a) return;
    if (oeffne(a.getAttribute('data-oeffnet'), true)) ev.preventDefault();
  });

  // Ankunft ueber einen Link von aussen (die Titelseite verlinkt
  // meldungen.html#ressort-netz) oder ueber die Adresszeile.
  function ausHash() {
    var id = (location.hash || '').replace(/^#/, '');
    if (id) oeffne(id, true);
  }
  window.addEventListener('hashchange', ausHash);
  ausHash();
})();

/* ===================================================================== *
 * Frag das Archiv (report/archiv_dossier.py als Browserfassung)
 *
 * Die Website ist eine Static Site OHNE Backend - das ist die Bedingung
 * dafuer, dass sie nie einschlaeft. Ein RAG-Aufbau braeuchte einen Dienst
 * zur Laufzeit, also gibt es hier BM25 im Browser und eine EXTRAKTIVE
 * Antwort: jede Zeile IST ein Archiveintrag, keine Umformulierung. Damit
 * kann eine Fussnote nicht auf etwas zeigen, das die Aussage nicht deckt.
 *
 * Die Konstanten unten muessen mit archiv_dossier.py uebereinstimmen -
 * ein Test haelt sie zusammen (test_archiv_dossier_js_und_python).
 * ===================================================================== */
var TelcoFrage = (function () {
  'use strict';

  var K1 = 1.5, B = 0.75, MIND_SCORE = 1.0, MAX_BELEGE = 8;
  var STOPP = ('der die das den dem des ein eine einen einem einer eines und '
    + 'oder aber auch mit von vom für fuer auf aus bei nach über ueber unter '
    + 'zwischen ist sind war waren wird werden wurde wurden hat haben hatte '
    + 'sich nicht kein keine als wie was wer wo wann warum welche welcher '
    + 'welches sein seine ihr ihre im in an am zu zum zur es sie er wir man '
    + 'mehr sehr schon noch nur dass denn doch so the and for of').split(' ');
  var STOPPSET = {};
  STOPP.forEach(function (w) { STOPPSET[w] = true; });

  function zerlege(text) {
    var treffer = String(text || '').toLowerCase()
      .match(/[a-zäöüßA-ZÄÖÜ0-9]{2,}/g) || [];
    return treffer.filter(function (w) { return !STOPPSET[w]; });
  }

  function baueIndex(items) {
    var docs = items.map(function (it) {
      return zerlege([it.title, it.summary, it.operator, it.category,
                      it.source_label].join(' '));
    });
    var df = {}, gesamt = 0;
    docs.forEach(function (d) {
      gesamt += d.length;
      var gesehen = {};
      d.forEach(function (w) {
        if (!gesehen[w]) { gesehen[w] = true; df[w] = (df[w] || 0) + 1; }
      });
    });
    var tf = docs.map(function (d) {
      var c = {};
      d.forEach(function (w) { c[w] = (c[w] || 0) + 1; });
      return c;
    });
    return { docs: docs, tf: tf, df: df, n: docs.length,
             avg: docs.length ? gesamt / docs.length : 0 };
  }

  function idf(idx, wort) {
    var d = idx.df[wort] || 0;
    return Math.log(1 + (idx.n - d + 0.5) / (d + 0.5));
  }

  function frage(items, text) {
    var worte = zerlege(text);
    if (!worte.length) {
      return { gefunden: false, belege: [],
               begruendung: 'Die Frage enthält keine durchsuchbaren Begriffe.' };
    }
    if (!items || !items.length) {
      return { gefunden: false, belege: [], begruendung: 'Das Archiv ist leer.' };
    }
    var idx = baueIndex(items);
    var einmalig = worte.filter(function (w, i) { return worte.indexOf(w) === i; });
    var bewertet = [];
    for (var i = 0; i < idx.n; i++) {
      if (!idx.docs[i].length) continue;
      var norm = K1 * (1 - B + B * idx.docs[i].length / (idx.avg || 1));
      var score = 0, getroffen = [];
      einmalig.forEach(function (w) {
        var f = idx.tf[i][w] || 0;
        if (!f) return;
        getroffen.push(w);
        score += idf(idx, w) * (f * (K1 + 1)) / (f + norm);
      });
      if (score >= MIND_SCORE) {
        bewertet.push({ score: score, treffer: getroffen, item: items[i] });
      }
    }
    if (!bewertet.length) {
      return { gefunden: false, belege: [], begruendung:
        'Dazu steht nichts im Archiv. Das heißt nicht, dass es nichts gibt — '
        + 'es heißt, dass keine der bisher erfassten Meldungen die Frage berührt.' };
    }
    bewertet.sort(function (a, b) {
      return b.score - a.score
        || String(b.item.date || '').localeCompare(String(a.item.date || ''));
    });
    var gesehen = {}, belege = [];
    for (var j = 0; j < bewertet.length && belege.length < MAX_BELEGE; j++) {
      var key = bewertet[j].item.url || bewertet[j].item.title || '';
      if (key && gesehen[key]) continue;
      gesehen[key] = true;
      belege.push(bewertet[j]);
    }
    return { gefunden: true, belege: belege, begruendung: '' };
  }

  function rendern(ziel, antwort) {
    if (!ziel) return;
    var esc = TelcoSearch.esc;
    if (!antwort.gefunden) {
      ziel.innerHTML = '<h2 class="rubrik">Was das Archiv dazu belegt</h2>'
        + '<p class="fa-leer">' + esc(antwort.begruendung) + '</p>';
      ziel.hidden = false;
      return;
    }
    var zeilen = antwort.belege.map(function (b) {
      var it = b.item;
      return '<li class="fa-beleg">'
        + '<b>' + esc(it.title || '') + '</b>'
        + (it.summary ? '<span>' + esc(it.summary) + '</span>' : '')
        + '<i>' + esc(it.source_label || it.operator || '')
        + (it.date ? ' · ' + esc(it.date) : '') + '</i>'
        + (it.url ? '<a href="' + esc(it.url) + '" rel="noopener">Quelle</a>' : '')
        + '</li>';
    }).join('');
    ziel.innerHTML = '<h2 class="rubrik">Was das Archiv dazu belegt</h2>'
      + '<p class="fa-hinweis">Jede Zeile ist eine erfasste Meldung im '
      + 'Wortlaut, keine Zusammenfassung. Was hier nicht steht, belegt das '
      + 'Archiv nicht.</p><ol class="fa-liste">' + zeilen + '</ol>';
    ziel.hidden = false;
  }

  return { zerlege: zerlege, frage: frage, rendern: rendern,
           K1: K1, B: B, MIND_SCORE: MIND_SCORE, MAX_BELEGE: MAX_BELEGE };
})();

/* Auf der Dossier-Seite: die Antwort steht ueber den Treffern. */
(function () {
  var ziel = document.getElementById('dossier-antwort');
  if (!ziel || typeof TelcoSearch === 'undefined') return;
  var eingabe = document.getElementById('dossier-input');
  function lauf() {
    var q = (eingabe && eingabe.value || '').trim();
    if (!q) { ziel.hidden = true; return; }
    TelcoSearch.loadIndex().then(function (items) {
      TelcoFrage.rendern(ziel, TelcoFrage.frage(items, q));
    });
  }
  lauf();
  if (eingabe) {
    eingabe.form && eingabe.form.addEventListener('submit', function () {
      setTimeout(lauf, 0);
    });
  }
})();

/* ---------------------------------------------------------------------- *
 * Geraeteradar: Reiter, Filter, Zeilenaufklapper.
 *
 * Alle Tafeln stehen fertig im HTML - hier wird nur umgeblendet, nichts
 * nachgeladen und nichts neu gerechnet. Genauso die Filter: sie BLENDEN
 * Zeilen aus, sie sortieren nicht um. Wer ohne JavaScript liest, sieht die
 * erste Tafel vollstaendig; das ist die Tafel, die die Frage der Seite
 * beantwortet.
 *
 * Bis zum 30.08.2026 stand hier der Umschalter der Positionskarte samt
 * Punktfilter. Die Grafik ist geloescht - 114 gedrehte Achsenbeschriftungen,
 * 155 von 164 Punkten ohne Beschriftung -, und mit ihr dieser Code.
 * ---------------------------------------------------------------------- */
(function () {
  var leiste = document.querySelector('.gr-reiter');
  if (!leiste) return;
  var knoepfe = leiste.querySelectorAll('button[data-tafel]');
  document.documentElement.setAttribute('data-art', 'tarif');

  var ARTEN = {'tafel-tco': 'tarif', 'tafel-verlauf': 'geraet'};
  function zeige(knopf) {
    var art = ARTEN[knopf.getAttribute('data-tafel')];
    if (art) {
      document.documentElement.setAttribute('data-art', art);
      document.dispatchEvent(new CustomEvent('gr-art', {detail: {art: art}}));
    }
    Array.prototype.forEach.call(knoepfe, function (k) {
      var ziel = document.getElementById(k.getAttribute('data-tafel'));
      var aktiv = k === knopf;
      k.setAttribute('aria-selected', aktiv ? 'true' : 'false');
      if (ziel) {
        ziel.classList.toggle('gr-tafel--aus', !aktiv);
        /* K (QA-Fix 24.09.2026): EIN EVENT FUER "JETZT SICHTBAR". Der
           Preisverlauf-Reiter zeichnet sein SVG mit der REALEN
           Containerbreite (`zeichne()` dort) - die ist an einer noch
           verborgenen Tafel 0. Statt dass dieser Umschalter etwas ueber
           den Chart-Code weiss, meldet er nur "diese Tafel ist jetzt
           aktiv"; wer davon abhaengt, hoert selbst zu. */
        if (aktiv) ziel.dispatchEvent(new CustomEvent('gr-tafel-sichtbar'));
      }
    });
  }

  Array.prototype.forEach.call(knoepfe, function (knopf) {
    knopf.addEventListener('click', function () { zeige(knopf); });
  });

  /* DEEP-LINKS AUF DIE ALTEN REITER DUERFEN NICHT INS LEERE FUEHREN.
   * Bis zum 04.09.2026 hiessen die Reiter `tafel-alarme` und `tafel-tco`,
   * und `#verlauf`, `#katalog`, `#tco` stehen als Sprungziele in Mails und
   * Lesezeichen. `#tafel-alarme` gibt es nicht mehr - ein solcher Link
   * landet jetzt auf der Hauptansicht statt auf einer Seite, die sich
   * scheinbar nicht bewegt.
   * Seit E3 Schritt 3 (17.09.2026) lebt der ganze Radar IN dieser Seite:
   * die Alt-URL des Radars ist eine Weiterleitung auf
   * #tafel-radar, deshalb schalten die Hash-Ziele des Radars (seine
   * Sektionen #wr-alarme/#wr-abweichung/#wr-haendler und das alte
   * Sprungziel #lifecycle aus der Portfolio-Zeit) den Radar-Reiter -
   * sonst spränge der Browser zu einem versteckten Element, ohne dass
   * die Tafel sichtbar würde. #wr-bewegungen (Wochenkarte) ist seit
   * P4 Schritt 2a (18.09.2026) in den Preisverlauf-Reiter verschoben
   * und schaltet seither DEN. */
  var ALT = {'tafel-alarme': 'tafel-tco', 'tco': 'tafel-tco',
             'katalog': 'tafel-katalog', 'verlauf': 'tafel-verlauf',
             'radar': 'tafel-radar', 'lifecycle': 'tafel-radar',
             'wr-alarme': 'tafel-radar', 'wr-abweichung': 'tafel-radar',
             'wr-haendler': 'tafel-radar', 'wr-bewegungen': 'tafel-verlauf'};
  function ausHash() {
    var id = (location.hash || '').replace(/^#/, '');
    if (!id) return;
    var ziel = ALT[id] || id;
    var knopf = leiste.querySelector('[data-tafel="' + ziel + '"]');
    if (knopf) zeige(knopf);
  }
  ausHash();
  window.addEventListener('hashchange', ausHash);
})();

/* P3 (Strategie Geraete v3, 17.09.2026): der EINE Ansichts-Umschalter
 * des Gerätekatalogs - Einzelgerätpreis <-> Gesamtkosten (TCO-24).
 *
 * Beide Ansichten stehen SERVERSEITIG fertig im Markup (eine Tabelle,
 * zwei Spaltengruppen); hier wird nur eine Klasse an der Tabelle
 * umgelegt, die die Spalten der jeweils anderen Ansicht ausblendet -
 * kein Reload, kein Rechnen, keine zweite Formatierung. Dieselbe
 * Bauform wie der Zeitraum- und der Band-Schalter der Seite
 * (`gr-vknopf`, aktiv ROT, `aria-pressed`).
 *
 * P4 Schritt 2c (18.09.2026): die Ansicht steht SEIT P4 in der URL
 * (?ansicht=tco) - der P3-Rest aus der Strategie. Ein geteilter Link
 * zeigt die angewählte Ansicht; der Parameter wird nur bei tco gesetzt
 * (barpreis ist die Grundfrage des Reiters und bleibt die kurze URL).
 * Der Zeitreihen-Block schreibt seine Parameter (?modell/&band) seit
 * derselben Änderung parameterweise statt die URL neu aufzubauen - ein
 * ansicht-Link überlebt damit jeden Modellwechsel. */
(function () {
  var tafel = document.getElementById('tafel-katalog');
  if (!tafel) return;
  var tabelle = document.getElementById('gr-katalogtabelle');
  var knoepfe = tafel.querySelectorAll('.gr-kansicht button[data-ansicht]');
  if (!tabelle || !knoepfe.length) return;

  function urlAnsicht(wert) {
    try {
      var p = new URLSearchParams(location.search);
      if (wert === 'tco') p.set('ansicht', 'tco');
      else p.delete('ansicht');
      var qs = p.toString();
      history.replaceState(null, '',
        (qs ? '?' + qs : location.pathname) + location.hash);
    } catch (e) { /* offline / file://: kein replaceState noetig */ }
  }

  function zeige(knopf, still) {
    tabelle.classList.toggle('gr-katalog--tco',
                             knopf.getAttribute('data-ansicht') === 'tco');
    Array.prototype.forEach.call(knoepfe, function (k) {
      var aktiv = k === knopf;
      k.classList.toggle('is-aktiv', aktiv);
      k.setAttribute('aria-pressed', aktiv ? 'true' : 'false');
    });
    if (!still) urlAnsicht(knopf.getAttribute('data-ansicht'));
    /* P3-Fix (Sicht-Pruefung Wesentliches 1, 18.09.2026): die Sortierung
       darf nicht an einer jetzt UNSICHTBAREN Spalte haengen bleiben.
       Gemessen am Live-Stand: nach "Einzelgeraepreis" (ab) sortiert und
       auf TCO umgeschaltet, standen die TCO-Werte unsortiert (3357.66 /
       2705.66 / 2927.80 ...), und der Sortierpfeil war weg - seine
       Kopfzelle war ausgeblendet. Der Filterblock der Tabelle
       (`grFilterleiste` unten) hoert auf dieses Event und uebernimmt die
       Sortierung fuer die neue Ansicht; hier wird nur gemeldet, nichts
       entschieden. */
    tabelle.dispatchEvent(new CustomEvent('gr-ansicht', {
      detail: {ansicht: knopf.getAttribute('data-ansicht')}
    }));
  }

  Array.prototype.forEach.call(knoepfe, function (knopf) {
    knopf.addEventListener('click', function () { zeige(knopf); });
  });

  /* Der Deep-Link beim Laden. Er laeuft UEBER zeige() (Klasse, Knopf-
     Markierung, Event) und nicht ueber einen nachgebauten Klick - ein
     knopf.click() wuerde denselben Weg nehmen, aber ein unbekannter
     Parameter bleibt ohne Folge (kein Fehler, kein Zurueckfallen). */
  try {
    var wunsch = new URLSearchParams(location.search).get('ansicht');
    var ziel = wunsch && tafel.querySelector(
      '.gr-kansicht button[data-ansicht="' + wunsch + '"]');
    if (ziel) zeige(ziel);
  } catch (e) { /* aeltere Browser: Grundansicht bleibt */ }

  /* Der Seitenschalter Mit Tarif / Einzelgerät (10.10.2026) gilt auch für
     die Tabelle "Alle Geräte": Tarif zeigt die Kosten über den Zeitraum,
     Einzelgerät den Gerätepreis. Ohne eigenen Leserwunsch keine URL. */
  function folgeArt(art) {
    var k = tafel.querySelector('.gr-kansicht button[data-ansicht="' +
      (art === 'geraet' ? 'barpreis' : 'tco') + '"]');
    if (k && k.getAttribute('aria-pressed') !== 'true') zeige(k, true);
  }
  document.addEventListener('gr-art', function (ev) { folgeArt(ev.detail.art); });
  if (!ziel) folgeArt(document.documentElement.getAttribute('data-art'));
})();

/* P4 SCHRITT 2c (STRATEGIE_GERAETE_V3, 18.09.2026): DER SPRUNG VOM RADAR
 * IN DEN KATALOG - die zweite Kante des roten Fadens zwischen den
 * Reitern. Der Link `a.gr-ksprung` (Modell-Zeile der Radar-Abweichungs-
 * liste) traegt denselben `modell_schluessel` wie die Katalog-Zeile
 * (`tr.gr-k-zeile[data-modell=...]`); dieser Handler schaltet den
 * Katalog-Reiter auf, legt die Zielzeile frei (aktive Filter werden
 * leer zurueckgesetzt, der Zeilen-Deckel ueber "alle anzeigen"
 * geoeffnet - sonst scrollte der Sprung an eine unsichtbare Zeile),
 * markiert sie EINMAL (.gr-k-ziel) und scrollt sie in Sicht.
 *
 * Ohne Zielzeile (der Link duerfte so nicht gerendert sein) laeuft der
 * Klick als gewoehnlicher Verweis: href ist der Reiter-Anker #katalog,
 * dessen Hash-Map den Reiter auch nach einem Reload aufschaltet. */
(function () {
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest ? ev.target.closest('a.gr-ksprung') : null;
    if (!a) return;
    var modell = a.getAttribute('data-modell');
    if (!modell) return;
    var zeile = document.querySelector(
      '#gr-katalogtabelle tr.gr-k-zeile[data-modell="' + modell + '"]');
    if (!zeile) return;
    ev.preventDefault();
    var knopf = document.querySelector(
      '.gr-reiter button[data-tafel="tafel-katalog"]');
    if (knopf) knopf.click();
    var tafel = document.getElementById('tafel-katalog');
    if (tafel) {
      Array.prototype.forEach.call(
        tafel.querySelectorAll('[data-filter]'), function (f) {
          if ((f.value || '') !== '') {
            f.value = '';
            f.dispatchEvent(new Event('change'));
          }
        });
    }
    if (zeile.classList.contains('gr-a-rest')) {
      var mehr = document.getElementById('gr-kmehr');
      if (mehr) mehr.click();
    }
    Array.prototype.forEach.call(
      document.querySelectorAll('.gr-k-ziel'),
      function (z) { z.classList.remove('gr-k-ziel'); });
    zeile.classList.add('gr-k-ziel');
    try {
      zeile.scrollIntoView({behavior: 'smooth', block: 'center'});
    } catch (e) { zeile.scrollIntoView(); }
  });
})();

/* O2 (STRATEGIE_GERAETE_OPTIK, 11.09.2026): die Bündel-Zeilen.
 *
 * Bis O2 sortierte dieser Block die Anbieterkarten der Klappe im Browser.
 * Die Karten sind Tabellenzeilen geworden: sie stehen SERVERSEITIG nach
 * TCO-24 sortiert (`geraete_tco_view._zeilen_rang`), der Anbieterfilter
 * ist entfallen (§4 Entscheidung 3). O3 bringt die SORTIERUNG der Zeilen
 * zurück (Auftrag C: TCO-24, Δ, Anbieter - ohne Reload), unten im
 * Graph-Block; die Bandwahl versteckt Zeilen anderer Bänder - derselbe
 * Handler wie für die Balken.
 */
/* O1 (STRATEGIE_GERAETE_OPTIK, 11.09.2026): DER EINE Graph - "TCO-24 je
 * Anbieter" für das gewählte Modell × Tarifband.
 *
 * NUR DAS VORGABEMODELL steht serverseitig im Dokument (bis O1 waren es
 * 88 Modellblöcke, 3,9 MB HTML). Dieser Block macht den Geräte-Selektor
 * für ALLE Modelle funktional: Titel, Antwortzeile und die Balkenzeilen
 * jedes Modells × Bandes kommen aus dem JSON-Knoten #gr-graph-daten -
 * denselben `balken`-Strukturen, die der Server für das Vorgabemodell
 * gerendert hat. ES WIRD NICHTS GERECHNET und nichts formatiert: alle
 * Zeichenketten (Wert, Δ, Legende) entstehen in Python, hier werden sie
 * nur gesetzt.
 *
 * O3 (15.09.2026): Auch die Bündel-ZEILEN folgen inzwischen dem Modell -
 * als fertiges Markup aus dem Fragment `data/geraete-buendel.html`
 * (siehe `setzeBuendel` unten), nicht als zweite Kartenkopie im Browser.
 */
/* E2 (AUFTRAG_GERAETE_EINE_SEITE_V2, 16.09.2026): die Steuerung der
 * TCO-ZEITREIHE. Dieser Block ist ein MONTAGEUR, kein Renderer: Antwort-
 * Satz, Messtag-Zeile, Legende, beide SVG-Varianten und Lueckensatz
 * kommen als FERTIGES Markup aus dem Fragment `data/geraete-zeitreihe.html`
 * (serverseitig aus demselben Makro wie der First Paint) und werden hier
 * nur eingesetzt. Kein Zahlbetrag geht je durch JavaScript - der JSON-
 * Knoten #gr-zeitreihe-daten traegt Titel, Zaehlungen und Erlaubnis.
 *
 * Suchfeld (§1b, genehmigt): Live-Vorschau ab 2 Zeichen, hoechstens 8
 * Treffer, klickbar vor vollstaendiger Eingabe; die Reihenfolge kommt
 * fertig und deterministisch aus Python (Bandabdeckung vor Auslaufware).
 */
(function () {
  var knoten = document.getElementById('gr-zeitreihe-daten');
  var zrGruppe = document.getElementById('gr-zr-gruppe');
  if (!knoten || !zrGruppe) return;
  var daten;
  try {
    daten = JSON.parse(knoten.textContent);
  } catch (e) {
    return;
  }
  if (!daten || !daten.vorgabe) return;

  /* Die Stufen der Vodafone-Tarifleiter (P3-E1) stehen im Datenknoten -
     kein zweiter, fest verdrahteter Katalog im Browser. */
  var BAND_KEYS = daten.band_folge || [];
  var zustand = { modell: daten.vorgabe,
                  band: daten.start_band || BAND_KEYS[0] || '',
                  laufzeit: String(daten.start_laufzeit || 24) };

  function element(id) { return document.getElementById(id); }

  /* Datenkonzept Geräte 5.4: die Ratenlaufzeit der Tafel - eine der Ansichten
     aus dem Datenknoten oder „alle“; alles andere fällt auf den Start zurück. */
  function laufzeitErlaubt(lz) {
    return lz === 'alle' ||
      (daten.laufzeiten || []).map(String).indexOf(lz) > -1;
  }

  /* --- Deep-Link ?modell=&band=&laufzeit= (bleibt: die 88 Sprung-Links der
     Abweichungstafel nutzen ?modell=, und Lesezeichen aus der Zeit der
     eigenen Radar-Seite ebenso). Eine unbekannte id faellt still aufs
     Startgeraet zurueck - derselbe Grundsatz wie zuvor. */
  try {
    var params = new URLSearchParams(location.search);
    var wunschM = params.get('modell');
    var wunschB = params.get('band');
    if (wunschM && (daten.erlaubt[wunschM] || []).length) {
      zustand.modell = wunschM;
    }
    if (wunschB && BAND_KEYS.indexOf(wunschB) > -1 &&
        (daten.erlaubt[zustand.modell] || []).indexOf(wunschB) > -1) {
      zustand.band = wunschB;
    } else {
      var erlaubtStart = daten.erlaubt[zustand.modell] || [];
      if (erlaubtStart.indexOf(zustand.band) === -1 && erlaubtStart.length) {
        zustand.band = erlaubtStart[0];
      }
    }
    var wunschL = params.get('laufzeit');
    if (wunschL && laufzeitErlaubt(wunschL)) zustand.laufzeit = wunschL;
  } catch (e) { /* aeltere Browser: Startzustand bleibt */ }

  /* --- Das Zeitreihen-Fragment: ALLE Paare, auch der Startzustand. Der
     Rueckweg nach einem Wechsel hat damit genau EINE Quelle - der alte
     Vorgabe-Klon (der bei einem Deep-Link Fremdes als "Vorgabe" einfrieren
     liess, S2) entfaellt fuer den Graphen komplett. */
  /* Seite schneller (10.10.2026): je Modell eine kleine Datei statt
     einer 47-MB-Gesamtdatei; ein fehlendes Modell (404) ist ein leeres
     Lager, kein Fehler. */
  var lagerCache = {};
  function holeLager(ordner, modell, auswahl, schluessel) {
    var url = 'data/' + ordner + '/' + encodeURIComponent(modell) + '.html';
    if (!lagerCache[url]) {
      lagerCache[url] = fetch(url)
        .then(function (r) {
          if (r.status === 404) return '';
          if (!r.ok) throw new Error(r.status);
          return r.text();
        })
        .then(function (txt) {
          var doc = new DOMParser().parseFromString(txt, 'text/html');
          var lager = {};
          Array.prototype.forEach.call(doc.querySelectorAll(auswahl),
            function (l) { lager[schluessel(l)] = l; });
          return lager;
        });
      lagerCache[url].catch(function () { delete lagerCache[url]; });
    }
    return lagerCache[url];
  }
  function holeZr(modell) {
    return holeLager('zr', modell, '.gr-zr-lager[data-modell]', function (l) {
      return l.getAttribute('data-modell') + '::' +
             l.getAttribute('data-band') + '::' +
             l.getAttribute('data-laufzeit');
    });
  }

  var zrFolge = 0;
  /* P1-Fix (Sicht-A1, 17.09.2026): der Karten-Preis oeffnet den Rechenweg
     DESSES Anbieters. Fuer eine NICHT aktive Karte muss erst das Paar
     geladen werden - der Wunsch ueberlebt den asynchronen Ladevorgang und
     wird nach dem Montieren des neuen Blocks bedient (oder still
     verworfen, wenn der Anbieter dort keine Vorlage hat: der Klick hat
     dann trotzdem Modell und Band gewechselt, nie ist er wirkungslos). */
  var zrOeffneNach = null;
  function zrWunschBedienen() {
    if (!zrOeffneNach) return;
    var wunsch = zrOeffneNach;
    zrOeffneNach = null;
    var serie = zrVorlagen(wunsch.anb);
    if (serie.length) {
      zrMessungOeffnen(wunsch.anb, serie[serie.length - 1]
        .getAttribute('data-m'));
    }
  }

  function setzeGraph(modell, band) {
    var folge = ++zrFolge;
    if (zustand.laufzeit === 'alle') {
      /* Über Laufzeiten hinweg gibt es keinen Sieger - also weder Antwort
         noch Graph, sondern den benannten Satz aus dem Datenknoten. */
      zrPanelSchliessen();
      zrOeffneNach = null;
      while (zrGruppe.firstChild) zrGruppe.removeChild(zrGruppe.firstChild);
      var satz = document.createElement('p');
      satz.className = 'gr-zr-keine gr-zr-alle';
      satz.textContent = daten.alle_text || '';
      zrGruppe.appendChild(satz);
      return;
    }
    holeZr(modell).then(function (lager) {
      if (folge !== zrFolge) return;
      var block = lager && lager[modell + '::' + band + '::' +
                                 zustand.laufzeit];
      while (zrGruppe.firstChild) zrGruppe.removeChild(zrGruppe.firstChild);
      /* P1/A2: ein offenes Panel gehoert zum PAAR, nicht zur Seite - sein
         Inhalt waere die Messung des eben entfernten Graphen. Im Fehlerfall
         (Fragment unerreichbar) bleibt der alte Block UND das Panel stehen. */
      zrPanelSchliessen();
      if (block) {
        var klon = document.importNode(block, true);
        while (klon.firstChild) zrGruppe.appendChild(klon.firstChild);
      } else if (lager) {
        var p = document.createElement('p');
        p.className = 'gr-zr-keine';
        p.textContent = 'Der Graph dieses Geräts konnte nicht geladen ' +
                        'werden – die Bündel-Zeilen darunter nennen die ' +
                        'Werte aller Anbieter.';
        zrGruppe.appendChild(p);
      }
      zrEingaengeRuesten();
      zrWunschBedienen();
    }, function () {
      if (folge !== zrFolge) return;
      /* Das Fragment ist unerreichbar: der SERVER-Startzustand bleibt
         stehen, statt einer leeren Flaeche. Ein bestellter Panel-Wunsch
         (Karten-Preis) ist damit unbezahlbar - er darf nicht auf den
         NAECHSTEN erfolgreichen Laden warten und dort ein fremdes Paar
         oeffnen. */
      zrOeffneNach = null;
    });
  }

  /* P1/A2 (17.09.2026, STRATEGIE_GERAETE_V3): das Klick-Panel fuer den
     RECHENWEG EINER Messung. Zwei Eingaenge, ein Ziel: der Klick auf den
     Kurvenpunkt (die unsichtbare Trefferflaeche .gr-zr-hit, r=12, UEBER dem
     gezeichneten Kreis) oder auf die PREISZAHL im Antwort-Satz setzt das
     fertige <template> dieser Messung in EIN Panel unter dem Graph -
     content.cloneNode, reine Montage. KEINE Zahl entsteht hier: kein
     Rechenoperator, kein Formatieren, kein Zusammensetzen von Betraegen
     (Regel 1 des Moduls; Schnittstelle
     outputs/strategie-geraete-v3-2026-09-17/p1/schnittstelle-rechenweg.md).

     Die Preiszahl nennt den besten Stand von HEUTE - zu "heute" gibt es kein
     Template. Der Klick oeffnet deshalb den Rechenweg des LETZTEN Messtags
     derselben Serie (DOM-last = juengste Messung; die Messtage je Serie sind
     serverseitig ISO-sortiert). Derselbe Klick schliesst wieder; ein Klick
     auf einen anderen Punkt wechselt die Messung; der aktive Punkt traegt
     eine sichtbare Markierung (in BEIDEN SVG-Varianten, denn das eine ist
     per CSS versteckt). */
  var zrPanel = element('gr-zr-panel');
  var zrMessung = null;           /* {anb, m} der offenen Messung */

  function zrVorlagen(anb) {
    var serie = [];
    Array.prototype.forEach.call(
      zrGruppe.querySelectorAll('.gr-zr-rechnungen template[data-anb]'),
      function (t) {
        if (t.getAttribute('data-anb') === anb) serie.push(t);
      });
    return serie;
  }

  function zrVorlage(anb, m) {
    var serie = zrVorlagen(anb);
    for (var i = 0; i < serie.length; i++) {
      if (serie[i].getAttribute('data-m') === m) return serie[i];
    }
    return null;
  }

  /* Der Anbieter der Preiszahl steht im Wortlaut des Antwort-Satzes,
     unmittelbar vor dem ersten fetten Betrag. Er wird nicht frei im Satz
     gesucht, sondern gegen die ANBIETERSCHLUESSEL des eigenen Blocks
     (data-anb der Vorlagen) in den drei festen Satzformen von
     _antwort_html: "ist X am günstigsten:", "führt X:", "führt nur X:".
     Der Browser-Test haelt Wortlaut und Klick zusammen. */
  function zrAnbieterDerPreiszahl() {
    var antwort = zrGruppe.querySelector('#gr-zr-antwort');
    var zahl = antwort && antwort.querySelector('b.gr-zr-zahl');
    if (!antwort || !zahl) return null;
    var text = '';
    for (var n = zahl.previousSibling; n && n.nodeType === 3;
         n = n.previousSibling) {
      text = n.data + text;
    }
    var treffer = [];
    Array.prototype.forEach.call(
      zrGruppe.querySelectorAll('.gr-zr-rechnungen template[data-anb]'),
      function (t) {
        var a = t.getAttribute('data-anb');
        if (treffer.indexOf(a) > -1) return;
        if (text.indexOf(a + ' am günstigsten:') > -1 ||
            text.indexOf('führt ' + a + ':') > -1 ||
            text.indexOf('führt nur ' + a + ':') > -1) treffer.push(a);
      });
    return treffer.length === 1 ? treffer[0] : null;
  }

  function zrPunkteMarkieren() {
    Array.prototype.forEach.call(
      zrGruppe.querySelectorAll('circle.gr-zr-punkt.gr-zr-aktiv'),
      function (c) { c.classList.remove('gr-zr-aktiv'); });
    if (!zrMessung) return;
    Array.prototype.forEach.call(
      zrGruppe.querySelectorAll('circle.gr-zr-punkt[data-anb]'),
      function (c) {
        if (c.getAttribute('data-anb') === zrMessung.anb &&
            c.getAttribute('data-m') === zrMessung.m) {
          c.classList.add('gr-zr-aktiv');
        }
      });
  }

  function zrPanelSchliessen() {
    zrMessung = null;
    if (zrPanel) {
      zrPanel.textContent = '';
      zrPanel.hidden = true;
    }
    zrPunkteMarkieren();
  }

  function zrPanelZeigen(vorlage) {
    if (!zrPanel) return;
    zrPanel.textContent = '';
    zrPanel.appendChild(document.importNode(vorlage.content, true));
    var zu = document.createElement('button');
    zu.type = 'button';
    zu.className = 'gr-zr-zu';
    zu.setAttribute('aria-label', 'Rechenweg schließen');
    zu.textContent = '×';
    zrPanel.appendChild(zu);
    zrPanel.hidden = false;
    /* Unter dem Graph, nicht neben dem Punkt (mobil instabil) - aber im
       Blickfeld des Klickenden, sobald der Graph hoeher als der Schirm
       ist. Gescrollt wird auf das PANEL, nicht die Rechnung: die Panel-
       Box traegt seit Sicht-A5 ein padding-bottom von 12 px - 'nearest'
       auf die Rechnung richtete deren Unterkante exakt an die Viewport-
       Kante (belegBottom == 844, null Luft, gemessen), 'nearest' auf das
       Panel nimmt die Polsterbox und schafft die 12 px. */
    try {
      zrPanel.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    } catch (e) { /* aeltere Browser: ohne Scroll ist das Panel trotzdem da */ }
  }

  function zrMessungOeffnen(anb, m) {
    if (zrMessung && zrMessung.anb === anb && zrMessung.m === m) {
      zrPanelSchliessen();        /* nochmals dieselbe Messung: zu */
      return;
    }
    zrMessung = {anb: anb, m: m};
    /* P1-Fix (Code-S3-2, 17.09.2026): die Vodafone-NAEHERUNG ist der
       Leerzustand FUER VODAFONE-Zahlen - nicht fuer fremde Anbieter. Bis
       hierher fiel ein o2-/Telekom-Punkt ohne Vorlage (Buendel unlesbar)
       auf die „Vodafone · Referenzrechnung": eine falsche Antwort auf
       „rechne MIR DIESE Messung vor". Fremde Messungen ohne Vorlage
       bekommen den ehrlichen Leer-Hinweis; nur Vodafone darf auf seine
       Naeherung fallen (deren Punkte haben keine Messung je Messtag,
       ihr benannter Leerzustand kommt als fertiges Template). */
    var vorlage = zrVorlage(anb, m);
    if (!vorlage && anb === 'Vodafone') {
      vorlage = zrVorlage('Vodafone', 'naeherung');
    }
    if (vorlage) {
      zrPanelZeigen(vorlage);
    } else if (zrPanel) {
      zrPanel.textContent = '';
      var p = document.createElement('p');
      p.className = 'gr-zr-rech gr-zr-rech--leer';
      p.textContent = 'Zu dieser Messung steht kein Rechenweg bereit.';
      zrPanel.appendChild(p);
      zrPanel.hidden = false;
    }
    zrPunkteMarkieren();
  }

  function zrPreiszahlOeffnen() {
    var anb = zrAnbieterDerPreiszahl();
    if (!anb) return;
    var serie = zrVorlagen(anb);
    if (!serie.length) return;
    var letzte = serie[serie.length - 1];
    zrMessungOeffnen(anb, letzte.getAttribute('data-m'));
  }

  /* Cursor, Fokus und Namen an den Eingaengen - die Flaeche selbst ist
     serverseitig da (A1); nach jedem Blockwechsel (neuer Graph) erneut,
     denn die Kreise sind dann neue Knoten.
     P1-Fix (Code-S3-3): die PREISZAHL bekommt Cursor/Tabindex/Titel nur,
     wenn der genannte Anbieter wirklich Vorlagen hat - ein fokussierbares,
     geklicktes Element ohne Antwort ist dasselbe halbtote Bedienelement,
     das B.3 bewusst nicht baute. Weggenommen wird die Ausstattung beim
     Blockwechsel genauso, wie sie gesetzt wird. */
  function zrEingaengeRuesten() {
    Array.prototype.forEach.call(
      zrGruppe.querySelectorAll('circle.gr-zr-hit[data-m]'),
      function (c) {
        if (c.getAttribute('tabindex') === '0') return;
        c.setAttribute('tabindex', '0');
        c.setAttribute('role', 'button');
        c.setAttribute('aria-label', 'Rechenweg öffnen: ' +
          c.getAttribute('data-anb') + ', Messung ' + c.getAttribute('data-m'));
      });
    var zahl = zrGruppe.querySelector('#gr-zr-antwort b.gr-zr-zahl');
    var anb = zrAnbieterDerPreiszahl();
    var hat = anb && zrVorlagen(anb).length > 0;
    if (zahl && hat) {
      zahl.classList.add('gr-zr-zahl--klick');
      zahl.setAttribute('tabindex', '0');
      zahl.setAttribute('title', 'Rechenweg dieser Messung öffnen');
    } else if (zahl) {
      zahl.classList.remove('gr-zr-zahl--klick');
      zahl.removeAttribute('tabindex');
      zahl.removeAttribute('title');
    }
  }

  function zrKlickZiel(ziel) {
    if (!ziel || !ziel.closest) return null;
    var kreis = ziel.closest('circle.gr-zr-hit[data-m]');
    if (kreis) return {anb: kreis.getAttribute('data-anb'),
                       m: kreis.getAttribute('data-m')};
    /* Nur die ERSTE Preiszahl des Satzes ist der Preis des genannten
       Anbieters - Ø/Monat und Delta gehoeren anderen Aussagen. */
    var erste = zrGruppe.querySelector('#gr-zr-antwort b.gr-zr-zahl');
    if (erste && ziel.closest('#gr-zr-antwort b.gr-zr-zahl') === erste) {
      return {preis: true};
    }
    return null;
  }

  zrGruppe.addEventListener('click', function (ev) {
    var ziel = zrKlickZiel(ev.target);
    if (!ziel) return;
    ev.preventDefault();
    if (ziel.preis) zrPreiszahlOeffnen();
    else zrMessungOeffnen(ziel.anb, ziel.m);
  });

  zrGruppe.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ' && ev.key !== 'Spacebar') return;
    var ziel = zrKlickZiel(ev.target);
    if (!ziel) return;
    ev.preventDefault();
    if (ziel.preis) zrPreiszahlOeffnen();
    else zrMessungOeffnen(ziel.anb, ziel.m);
  });

  /* Der Schliessen-Knopf des Panels - als Delegation, denn der Knopf wird
     mit jedem geoeffneten Rechenweg neu erzeugt. */
  if (zrPanel) {
    zrPanel.addEventListener('click', function (ev) {
      if (ev.target && ev.target.closest &&
          ev.target.closest('.gr-zr-zu')) zrPanelSchliessen();
    });
  }

  /* --- Die Buendel-Zeilen folgen dem Modell (O3, unveraendert): Fragment,
     Klon des Anfangszustands, eigene Folgen. E3-Fix (QA 17.09.2026): der
     G0-Block des Verlaufs-Reiters ist gefallen - er zeigte den Barpreis
     des VERGLEICHS-Reiter-Modells neben der eigenen Auswahl desselben
     Reiters (Doppel-Darstellung, §4.6/§4.8). */
  var vorgabeGruppe = null;
  var wechselFolge = 0;
  var zuletztModell = null;
  var vorgabe = daten.vorgabe;

  (function () {
    var anfangsGruppe = element('gr-bnd-gruppe');
    if (anfangsGruppe) vorgabeGruppe = anfangsGruppe.cloneNode(true);
  })();

  function holeFragment(modell) {
    return holeLager('bnd', modell, '.gr-bnd-lager[data-modell]', function (l) {
      return l.getAttribute('data-modell');
    });
  }

  function gruppeLeeren(gruppe) {
    while (gruppe.firstChild) gruppe.removeChild(gruppe.firstChild);
  }

  function setzeBndTitel(mid, band) {
    var titel = element('gr-bnd-titel');
    if (!titel) return;
    var m = daten.bnd_titel[mid] || {};
    if (band && m[band]) titel.textContent = m[band];
    else if (daten.bnd_titel_ohne[mid]) titel.textContent =
      daten.bnd_titel_ohne[mid];
  }

  function leerSatz(gruppe, text) {
    var p = document.createElement('p');
    p.className = 'gr-erklaer';
    p.textContent = text;
    gruppe.appendChild(p);
  }

  function setzeBuendel(mid, bandKey) {
    var gruppe = element('gr-bnd-gruppe');
    if (!gruppe) return;
    var fertig = function (knotenB, fehler) {
      gruppeLeeren(gruppe);
      /* Die Bündelliste ist weg (Antonio, 10.10.2026): vom Lager kommt nur
         die Zeile der fehlenden Anbieter auf die Seite. */
      if (knotenB) {
        var klon = document.importNode(knotenB, true);
        Array.prototype.forEach.call(
          klon.querySelectorAll('.gr-anb-fehlliste'),
          function (f) { gruppe.appendChild(f); });
      } else if (fehler) {
        leerSatz(gruppe, 'Fehlende Anbieter nicht geladen.');
      }
      setzeBndTitel(mid, bandKey);
      stelleZeilen(bandKey);
      wendeSortierungAn();
    };
    if (mid === vorgabe) {
      fertig(vorgabeGruppe, false);
      return;
    }
    var meineFolge = ++wechselFolge;
    holeFragment(mid).then(function (lager) {
      if (meineFolge !== wechselFolge) return;
      fertig(lager ? lager[mid] : null, false);
    }, function () {
      if (meineFolge !== wechselFolge) return;
      fertig(null, true);
    });
  }

  /* O2/C: die sortierbare Buendeltabelle.

     P0-B-z2: DER RANG GILT NUR INNERHALB EINES ZEITRAUMS. Ein Klick auf
     den Kopf sortierte nach `data-gesamt` allein - damit rangierte die
     36-Monats-Summe von 1&1 (2.019,54 EUR) zwischen den 24-Monats-Summen
     derselben Liste, also als waere sie teurer als eine Zahl, mit der sie
     nicht vergleichbar ist. Beide Ausgaenge waeren falsch gewesen: die
     Zeile stillschweigend mitsortieren ODER sie aus der Liste nehmen
     (Meldungen werden nie gekappt).
     Deshalb sortiert der TCO-Rang jetzt ZWEISTUFIG: erst der Zeitraum
     (`data-leitzahl-monate`, aus `Tco.leitzahl_monate` - gelesen, nicht
     gerechnet), dann der Betrag INNERHALB dieses Zeitraums. Die
     Zeitraeume selbst stehen immer aufsteigend (kuerzerer zuerst) und
     drehen mit der Richtung NICHT mit: der Zeitraum ist kein Wert, der
     rangiert, sondern der Rahmen, in dem ueberhaupt rangiert wird. Jede
     Zeile nennt ihren Rahmen selbst - das Etikett an ihrer Summe.
     Die Δ-Spalte braucht das nicht: ein Δ ueber zwei Zeitraeume gibt es
     nicht (`geraete_tco_karten.delta_zustand`), diese Zeilen tragen
     `data-delta=""` und stehen schon am Ende. */
  var sortierung = {key: null, richtung: 1};
  var sortierKnoepfe = document.querySelectorAll('#gr-buendel .gr-bsort');

  function sortierWert(z) {
    if (sortierung.key === 'anbieter') {
      return z.getAttribute('data-anbieter') || '';
    }
    var attr = sortierung.key === 'tco' ? 'data-gesamt' : 'data-delta';
    var roh = z.getAttribute(attr);
    if (roh === null || roh === '') return null;
    var zahl = parseFloat(roh);
    return isNaN(zahl) ? null : zahl;
  }

  /* Der Zeitraum, den die Summe dieser Zeile traegt - GELESEN aus dem
     Attribut, das die Vorlage aus `leitzahl_monate` schreibt. Ohne
     gemessenen Zeitraum `null`: diese Zeilen tragen auch keine belastbare
     Summe und stehen hinter allen Zeitraeumen. */
  function zeitraumVon(z) {
    var roh = z.getAttribute('data-leitzahl-monate');
    if (roh === null || roh === '') return null;
    var zahl = parseInt(roh, 10);
    return isNaN(zahl) ? null : zahl;
  }

  function wendeSortierungAn() {
    if (!sortierung.key) return;
    var richt = sortierung.richtung;
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-buendel .gr-bndliste'),
      function (liste) {
        var zeilen = Array.prototype.filter.call(
          liste.children,
          function (k) {
            return k.classList && k.classList.contains('gr-bnd');
          });
        zeilen.sort(function (x, y) {
          if (sortierung.key === 'tco') {
            var zx = zeitraumVon(x), zy = zeitraumVon(y);
            if (zx !== zy) {
              if (zx === null) return 1;
              if (zy === null) return -1;
              return zx - zy;
            }
          }
          var kx = sortierWert(x), ky = sortierWert(y);
          if (kx === null && ky === null) return 0;
          if (kx === null) return 1;
          if (ky === null) return -1;
          if (typeof kx === 'string' || typeof ky === 'string') {
            return kx.localeCompare(ky, 'de') * richt;
          }
          return (kx - ky) * richt;
        });
        zeilen.forEach(function (z) { liste.appendChild(z); });
        if (zustand.laufzeit === 'alle') ordneNachLaufzeit(liste);
      });
  }

  function markiereSortierung() {
    Array.prototype.forEach.call(sortierKnoepfe, function (knopf) {
      var aktiv = knopf.getAttribute('data-bsort') === sortierung.key;
      knopf.classList.toggle('ist-auf', aktiv && sortierung.richtung > 0);
      knopf.classList.toggle('ist-ab', aktiv && sortierung.richtung < 0);
    });
  }

  Array.prototype.forEach.call(sortierKnoepfe, function (knopf) {
    knopf.addEventListener('click', function () {
      var key = knopf.getAttribute('data-bsort');
      if (sortierung.key === key) {
        sortierung.richtung = -sortierung.richtung;
      } else {
        sortierung.key = key;
        sortierung.richtung = 1;
      }
      markiereSortierung();
      wendeSortierungAn();
    });
  });

  /* Datenkonzept Geräte Schritt 3: die Zeilen folgen dem Umschalter der
     Ratenlaufzeit (`zustand.laufzeit`). Unter welcher Wahl eine Zeile steht,
     entscheidet Python (`data-lz`, geraete_laufzeit.setze_ansicht); hier wird
     nur geblendet. Unter „alle“ stehen die Zeilen nach Laufzeit gruppiert -
     stabil umgeordnet, mit den Köpfen der Vorlage - und ohne Δ. */
  function lzRang(z) {
    var lz = parseInt(z.getAttribute('data-lz'), 10);
    return isNaN(lz) ? 1e9 : lz;
  }

  function ordneNachLaufzeit(liste) {
    var paare = Array.prototype.filter.call(liste.children, function (k) {
      return k.classList && k.classList.contains('gr-bnd');
    }).map(function (z, i) { return [z, i]; });
    paare.sort(function (a, b) {
      return (lzRang(a[0]) - lzRang(b[0])) || (a[1] - b[1]);
    });
    paare.forEach(function (p) { liste.appendChild(p[0]); });
    Array.prototype.forEach.call(
      liste.querySelectorAll('.gr-bnd-lzkopf'),
      function (kopf) {
        var lz = kopf.getAttribute('data-lz-kopf');
        var erste = null;
        paare.some(function (p) {
          if (p[0].hidden || (p[0].getAttribute('data-lz') || '') !== lz) {
            return false;
          }
          erste = p[0];
          return true;
        });
        kopf.hidden = !erste;
        if (erste) liste.insertBefore(kopf, erste);
      });
  }

  function stelleZeilen(band) {
    var lz = zustand.laufzeit;
    var alle = lz === 'alle';
    var sektion = element('gr-buendel');
    if (sektion) sektion.classList.toggle('gr-buendel--alle', alle);
    var zeilen = document.querySelectorAll(
      '#gr-bnd-gruppe .gr-bnd, #gr-bnd-gruppe .gr-anb-fehlt');
    Array.prototype.forEach.call(zeilen, function (z) {
      var bandAus = !!band && z.hasAttribute('data-band')
        && z.getAttribute('data-band') !== band;
      var lzAus = !alle && z.hasAttribute('data-lz')
        && z.getAttribute('data-lz') !== lz;
      if (z.hasAttribute('data-fehlt-lz')) {
        lzAus = z.getAttribute('data-fehlt-lz') !== lz;
      }
      z.hidden = bandAus || lzAus;
    });
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-bnd-gruppe .gr-bndliste'),
      function (liste) {
        if (alle) {
          ordneNachLaufzeit(liste);
          return;
        }
        Array.prototype.forEach.call(
          liste.querySelectorAll('.gr-bnd-lzkopf'),
          function (kopf) { kopf.hidden = true; });
      });
    /* „Ohne Tarifband“ ohne eine sichtbare Zeile dieser Laufzeit und ohne
       Händlerpreis stünde als leerer Kopf da - die Gruppe tritt zurück. */
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-bnd-gruppe .gr-ohneband'),
      function (gruppe) {
        gruppe.hidden = !Array.prototype.some.call(
          gruppe.querySelectorAll('.gr-bnd, .gr-haendlerzeile'),
          function (z) { return !z.hidden; });
      });
  }

  /* --- Die Wahl: Band-Knoepfe, Kacheln, Suchfeld --------------------- */
  function markiereBaender() {
    var erlaubt = daten.erlaubt[zustand.modell] || [];
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-zr-baender button[data-band]'),
      function (k) {
        var band = k.getAttribute('data-band');
        k.disabled = erlaubt.indexOf(band) === -1;
        k.setAttribute('aria-pressed', band === zustand.band ? 'true'
                                                             : 'false');
      });
  }

  function markiereKacheln() {
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-zr-kacheln button[data-modell]'),
      function (k) {
        k.setAttribute('aria-pressed',
                       k.getAttribute('data-modell') === zustand.modell
                         ? 'true' : 'false');
      });
  }

  /* P1-Fix (Sicht-B2, 17.09.2026): die Modell-Karten tragen ihre Werte JE
     BAND als fertige Spans (serverseitig, Regel 1) - der Bandwechsel
     blendet nur um (hidden, reine Attributmontage). Bis hierher zeigten
     die Karten in jedem Band denselben bandunabhaengigen "ab"-Preis und
     der Umschalter wirkte auf die prominenteste Ebene nicht. Eine Karte,
     die das gewählte Band nicht führt, zeigt ihren Ersatz-Span („-"),
     statt komplett leer zu stehen. */
  function setzeKartenBand(band) {
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-zr-kacheln button[data-modell]'),
      function (k) {
        var traf = false;
        Array.prototype.forEach.call(
          k.querySelectorAll('.gr-zr-k-band[data-band]'),
          function (s) {
            var passt = s.getAttribute('data-band') === band &&
              s.getAttribute('data-lz') === zustand.laufzeit;
            s.hidden = !passt;
            if (passt) traf = true;
          });
        var alle = zustand.laufzeit === 'alle';
        var ersatz = k.querySelector('.gr-zr-k-band--kein');
        if (ersatz) ersatz.hidden = traf || alle;
        var ohneSieger = k.querySelector('.gr-zr-k-band--alle');
        if (ohneSieger) ohneSieger.hidden = !alle;
      });
  }

  function setzeSuchfeld() {
    var feld = element('gr-zr-suche');
    if (feld) feld.value = daten.titel[zustand.modell] || '';
    var treffer = element('gr-zr-treffer');
    if (treffer) {
      var n = (daten.erlaubt[zustand.modell] || []).length;
      treffer.textContent = n ? n + (n === 1 ? ' Band' : ' Bänder')
                              : daten.modelle_gesamt + ' Modelle';
    }
  }

  /* EINE Wahl beendet die Suche - egal ob der Treffer per Klick, Enter,
     Kachel oder Band gewaehlt wurde. Die offene Vorschau verdeckte auf
     dem Telefon die Band-Knoepfe und die Kacheln komplett (E2-F3: der
     Band-Klick schlug 60-mal am Overlay fehl), und der alte blur-Timer
     feuerte nach der Auswahl oft nicht - der mousedown-Handler der
     Eintraege ruft preventDefault und haelt damit den Fokus. */
  function schliesseVorschau() {
    var box = element('gr-zr-vorschau');
    if (box) box.textContent = '';
  }

  function markiereLaufzeiten() {
    Array.prototype.forEach.call(
      document.querySelectorAll('#gr-zr-laufzeiten button[data-lz]'),
      function (k) {
        k.setAttribute('aria-pressed', k.getAttribute('data-lz') ===
                       zustand.laufzeit ? 'true' : 'false');
      });
  }

  /* P4 Schritt 2c: parameterweise statt die URL neu aufzubauen - ein
     ?ansicht=-Deep-Link des Katalogs ueberlebt so jeden Wechsel (bis P4
     loeschte dieser Neuaufbau alle Nachbarn). */
  function schreibeLink() {
    try {
      var p = new URLSearchParams(location.search);
      p.set('modell', zustand.modell);
      p.set('band', zustand.band);
      p.set('laufzeit', zustand.laufzeit);
      history.replaceState(null, '', '?' + p.toString() + location.hash);
    } catch (e) { /* Datei-Offline: kein replaceState noetig */ }
  }

  /* Datenkonzept Geräte 5.4: auch der Bündel-Export folgt dem Umschalter.
     Ziel und Text je Ansicht stehen fertig in den data-Feldern des Links
     (`geraete_export.schreibe_exporte`, `tco_je_laufzeit`); ohne Feld bleibt
     der Link, wie er ist. */
  function setzeExport() {
    var link = element('gr-export-tco');
    var datei = link && link.getAttribute('data-datei-' + zustand.laufzeit);
    if (!datei) return;
    link.setAttribute('href', datei);
    link.textContent = link.getAttribute('data-text-' + zustand.laufzeit);
  }

  function waehleLaufzeit(lz) {
    if (!laufzeitErlaubt(lz) || lz === zustand.laufzeit) return;
    zustand.laufzeit = lz;
    zrOeffneNach = null;
    markiereLaufzeiten();
    setzeKartenBand(zustand.band);
    setzeGraph(zustand.modell, zustand.band);
    stelleZeilen(zustand.band);
    setzeExport();
    schreibeLink();
  }

  function waehle(modell, band) {
    schliesseVorschau();
    /* Ein Panel-Wunsch (Karten-Preis, Sicht-A1) ueberlebt keinen NEUEN
       Wahlweg - nur den Ladevorgang des Paars, das er bestellt hat. */
    zrOeffneNach = null;
    var erlaubt = daten.erlaubt[modell] || [];
    if (!erlaubt.length) return;
    zustand.modell = modell;
    TR_LESER_MODELL = modell;
    if (band && erlaubt.indexOf(band) > -1) {
      zustand.band = band;
    } else if (erlaubt.indexOf(zustand.band) === -1) {
      zustand.band = erlaubt[0];
    }
    markiereBaender();
    markiereKacheln();
    setzeKartenBand(zustand.band);
    setzeSuchfeld();
    setzeGraph(zustand.modell, zustand.band);
    setzeBndTitel(zustand.modell, zustand.band);
    stelleZeilen(zustand.band);
    if (zustand.modell !== zuletztModell) {
      zuletztModell = zustand.modell;
      setzeBuendel(zustand.modell, zustand.band);
    }
    schreibeLink();
  }

  /* Gegenstueck zu „Ohne Vertrag“ (siehe `leserGeraet` dort): wird dieser
     Reiter sichtbar und hat der Leser ein anderes Geraet gewaehlt, das
     hier Buendel hat, zeigt er dieses. */
  var tcoTafel = element('tafel-tco');
  if (tcoTafel) {
    tcoTafel.addEventListener('gr-tafel-sichtbar', function () {
      var id = TR_LESER_MODELL;
      if (id && id !== zustand.modell && (daten.erlaubt[id] || []).length) {
        waehle(id);
      }
    });
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('#gr-zr-baender button[data-band]'),
    function (k) {
      k.addEventListener('click', function () {
        if (k.disabled) return;
        waehle(zustand.modell, k.getAttribute('data-band'));
      });
    });

  Array.prototype.forEach.call(
    document.querySelectorAll('#gr-zr-laufzeiten button[data-lz]'),
    function (k) {
      k.addEventListener('click', function () {
        waehleLaufzeit(k.getAttribute('data-lz'));
      });
    });

  Array.prototype.forEach.call(
    document.querySelectorAll('#gr-zr-kacheln button[data-modell]'),
    function (k) {
      k.addEventListener('click', function (ev) {
        var modell = k.getAttribute('data-modell');
        /* P1-Fix (Sicht-A1, 17.09.2026): Klick auf die PREISZAHL der
           Karte oeffnet zusaetzlich den Rechenweg dieses Preises -
           Antonios Geste ist „wenn man auf den Preis drueckt". Der
           Band-Koerper traegt serverseitig data-anb (Anbieter des
           ab-Preises); die Vorlagen des Paars stehen erst nach dessen
           Wechsel im DOM, deshalb bestellt der Klick Modell UND Band und
           hinterlasst einen Wunsch (zrOeffneNach), den der geladene Block
           bedient. Ohne Anbieter ("-", Band ohne echtes Angebot) bleibt
           der gewoehnliche Wahl-Klick - kein Bedienelement ohne Antwort.
           Kein Zahlbetrag geht durch diese Hand: nur Attribute. */
        var ziel = ev.target && ev.target.closest
          ? ev.target : null;
        var koerper = ziel && ziel.closest('.gr-zr-k-band[data-anb]');
        if (koerper && ziel.closest('.gr-zr-k-preis')) {
          var band = koerper.getAttribute('data-band');
          zrOeffneNach = null;
          waehle(modell, band);
          zrOeffneNach = {anb: koerper.getAttribute('data-anb')};
          return;
        }
        waehle(modell, null);
      });
    });

  /* E3/S2: DER SPRUNG AUS DER RADAR-MODELLLISTE in den Graphen dieses
     Reiters. Der Link trägt den Deep-Link (?modell=…&band=…) und
     funktioniert auch ohne JavaScript als Seitenaufruf; hier wird er
     in-page beantwortet: Reiter umschalten (der programmatische Klick auf
     den vorhandenen Reiter-Knopf löst dessen Handler aus), Modell und
     Band wählen, zum Graphen scrollen. Ein Modell ohne Zeitreihe
     (`erlaubt` leer) wird dem Link überlassen - der Reload fällt laut
     Deep-Link-Regel oben still aufs Startgerät zurück. */
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest ? ev.target.closest('a.gr-sprung') : null;
    if (!a) return;
    var modell = a.getAttribute('data-modell');
    if (!modell || !(daten.erlaubt[modell] || []).length) return;
    ev.preventDefault();
    var knopf = document.querySelector(
      '.gr-reiter button[data-tafel="tafel-tco"]');
    if (knopf) knopf.click();
    waehle(modell, a.getAttribute('data-band'));
    var ziel = document.getElementById('gr-zr-gruppe');
    if (ziel) ziel.scrollIntoView({behavior: 'smooth', block: 'start'});
  });

  /* P4-Fix (Sicht-Pruefung 18.09., Kriterium 13): der RECHENWEG der
     Bündel-Zeilen steht im <template> neben dem Aufklapper und wird
     ERST BEIM ÖFFNEN montiert - derselbe Weg wie der P1-Rechenweg-Pool
     der Zeitreihe (FM 4: der Aufklapp-Text zaehlte 18 048 der
     Fliesstext-Zeichen des Vergleichs-Reiters, der Deckel ist 6000).
     Montage ist reines DOM-Verschieben: content.cloneNode, keine Zahl
     wird hier gelesen oder gerechnet. Der click-Delegat greift fuer
     Seite UND lazy-Fragment (beide entstehen aus demselben Makro);
     das Oeffnen ist die Default-Aktion des summary-Klicks und laeuft
     NACH diesem Handler - der Zielzustand ist das Gegenteil des
     aktuellen. */
  function montiereRechenweg(details) {
    var zielDiv = details.querySelector('.gr-bnd-rw');
    var vorlage = details.querySelector('template.gr-bnd-rw-vorlage');
    if (!zielDiv || !vorlage || zielDiv.firstChild) return;
    zielDiv.appendChild(vorlage.content.cloneNode(true));
  }
  document.addEventListener('click', function (ev) {
    var s = ev.target && ev.target.closest
      ? ev.target.closest('details.gr-bnd > summary') : null;
    if (!s) return;
    var d = s.parentNode;
    if (d && d.tagName === 'DETAILS' && !d.hasAttribute('open')) {
      montiereRechenweg(d);
    }
  });
  /* Doppelter Weg, einfache Sicherung: toggle feuert (Capture faengt
     das nicht-bubbelnde Event) auch fuer Oeffnungen ohne click-Handler -
     beide Wege sind idempotent (montiereRechenweg prueft firstChild). */
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (d && d.tagName === 'DETAILS' && d.classList &&
        d.classList.contains('gr-bnd') && d.open) {
      montiereRechenweg(d);
    }
  }, true);

  /* Die Live-Vorschau: ab 2 Zeichen, hoechstens 8 Treffer, Praefix-Treffer
     auf Titel-Woertern - die Reihenfolge kommt fertig aus Python. */
  function trefferListe(eingabe) {
    var tokens = eingabe.toLowerCase().split(/\s+/).filter(Boolean);
    return daten.suchindex.filter(function (s) {
      var worte = (s.titel || '').toLowerCase().split(/[\s·]+/).filter(Boolean);
      return tokens.every(function (t) {
        return worte.some(function (w) { return w.indexOf(t) === 0; });
      });
    }).slice(0, 8);
  }

  function vorschau(wert) {
    var box = element('gr-zr-vorschau');
    var treffer = element('gr-zr-treffer');
    if (!box) return;
    if (wert.trim().length < 2) { box.textContent = ''; return; }
    var liste = trefferListe(wert.trim());
    if (treffer) {
      treffer.textContent = liste.length
        ? liste.length + ' Treffer'
        : 'kein Treffer';
    }
    box.textContent = '';
    /* P5-Live-Pruefung R3: 0 Treffer, aber der KATALOG kennt den Begriff -
     * das Modell ist zu neu fuer die Wahl (Bündel mit erst einem Messtag).
     * EINE Zeile mit dem fruehesten Belegdatum, als gr-ksprung auf die
     * Katalog-Zeile (derselbe Handler wie die Radar-Liste: Reiter auf,
     * Deckel oeffnen, Zeile markieren). Ohne Katalog-Treffer bleibt die
     * Box leer - "kein Treffer" braucht keinen Zusatz. */
    if (!liste.length) {
      var tokens = wert.trim().toLowerCase().split(/\s+/).filter(Boolean);
      var neu = (daten.katalog_neu || []).filter(function (s) {
        var worte = (s.titel || '').toLowerCase().split(/[\s·]+/)
          .filter(Boolean);
        return tokens.every(function (t) {
          return worte.some(function (w) { return w.indexOf(t) === 0; });
        });
      });
      if (neu.length) {
        var a = document.createElement('a');
        var aelteste = neu[0];
        neu.forEach(function (s) {
          if (s.iso && (!aelteste.iso || s.iso < aelteste.iso)) aelteste = s;
        });
        a.className = 'gr-ksprung gr-zr-v-neu';
        a.href = '#katalog';
        a.setAttribute('data-modell', aelteste.id);
        a.textContent = 'Neu seit ' + (aelteste.datum || 'kurzem') +
          ' – im Katalog ansehen';
        box.appendChild(a);
      }
      return;
    }
    liste.forEach(function (s) {
      var b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('role', 'option');
      b.setAttribute('data-modell', s.id);
      var titel = document.createElement('span');
      titel.className = 'gr-zr-v-titel';
      titel.textContent = s.titel;
      var meta = document.createElement('span');
      meta.className = 'gr-zr-v-meta';
      /* Die GB-Stufe steht schon im Titel - sie noch einmal in die Meta-
         Zeile zu setzen hiesse dieselbe Zahl zweimal in einer Zeile. */
      meta.textContent = s.anbieter_zahl + ' Anbieter · ' +
        (s.band_zahl === 1 ? '1 Band' : s.band_zahl + ' Bänder');
      b.appendChild(titel);
      b.appendChild(meta);
      b.addEventListener('mousedown', function (ev) {
        ev.preventDefault();
        waehle(s.id, null);
      });
      box.appendChild(b);
    });
  }

  var feld = element('gr-zr-suche');
  if (feld) {
    feld.addEventListener('input', function () { vorschau(feld.value); });
    feld.addEventListener('focus', function () {
      /* E2-F2: Das Feld traegt den Titel des gewaehlten Geraets als
         Vorbelegung - Antippen und Schreiben soll ERSETZEN (Antonios
         Weg: „pixel 11 tippen"), nicht anhaengen. Der Fokus markiert
         deshalb die ganze Vorbelegung; das erste Zeichen loescht sie. */
      try { feld.setSelectionRange(0, feld.value.length); } catch (e) {}
      /* Die UNVERAENDERTE Vorbelegung oeffnet die Vorschau nicht: ihre
         Trefferliste waere das aktuelle Geraet allein, und auf dem
         Telefon wuerde sie nur die Band-Knoepfe verdecken (E2-F3). Erst
         eigene Eingabe (oder der Fokus nach einer Suche ohne Wahl)
         oeffnet sie. */
      if (feld.value !== (daten.titel[zustand.modell] || '')) {
        vorschau(feld.value);
      }
    });
    /* EIN Tap ausserhalb von Feld und Vorschau schliesst die Liste - er
       darf nicht vom blur-Timing abhaengen. Capture: der Closer steht
       damit VOR jedem Klick-Handler des Ziels (E2-F3). */
    document.addEventListener('pointerdown', function (ev) {
      var ziel = ev.target;
      if (feld.contains(ziel)) return;
      var box = element('gr-zr-vorschau');
      if (box && box.contains(ziel)) return;
      schliesseVorschau();
    }, true);
    feld.addEventListener('blur', function () {
      setTimeout(schliesseVorschau, 150);
    });
    feld.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        schliesseVorschau();
      }
      if (ev.key === 'Enter') {
        var erster = element('gr-zr-vorschau') &&
                     element('gr-zr-vorschau').querySelector('button');
        if (erster) {
          ev.preventDefault();
          waehle(erster.getAttribute('data-modell'), null);
        }
      }
    });
  }

  /* --- Start: der Server-Zustand steht da; dieser Aufruf setzt nur die
     Markierungen und blendet die Zeilen des gewaehlten Bands ein. Ein
     Deep-Link-Band, das vom Server-Start abweicht, schaltet auch die
     Karten-Spans um (Sicht-B2) - der Server rendert sein Startband. */
  markiereBaender();
  markiereLaufzeiten();
  markiereKacheln();
  setzeKartenBand(zustand.band);
  setzeSuchfeld();
  stelleZeilen(zustand.band);
  setzeExport();
  /* P1/A2: der First Paint steht serverseitig da (setzeGraph lief noch
     nicht) - seine Kreise und die Preiszahl brauchen Cursor und Fokus. */
  zrEingaengeRuesten();
  /* zuletztModell beschreibt, WAS IM DOM STEHT - und das ist am Anfang
     der SERVER-First-Paint, also das Startmodell (vorgabe), NICHT der
     Deep-Link-Wunsch. Stand es auf dem Wunsch, traf der erste waehle()-
     Aufruf auf "bereits gewechselt" und liess die Buendel-Zeilen des
     Startmodells stehen, waehrend Graph und Antwort schon das Deep-Link-
     Geraet zeigten (gemessen am o3-Rueckwechseltest: 4 Zeilen des
     Startmodells unter einem s26-Deep-Link). */
  zuletztModell = vorgabe;
  schreibeLink();
  /* Ein Deep-Link auf ein ANDERES Geraet als den Server-Startzustand
     braucht den ersten Fragmentabruf - sonst zeigten Graph und Tabelle
     das Startgeraet, obwohl die URL ein anderes nennt. Dasselbe gilt fuer
     ein anderes Band oder eine andere Laufzeit desselben Geraets: der
     Server rendert nur sein Startpaar. */
  if (zustand.modell !== vorgabe) {
    waehle(zustand.modell, zustand.band);
  } else if (zustand.band !== daten.start_band ||
             zustand.laufzeit !== String(daten.start_laufzeit)) {
    setzeGraph(zustand.modell, zustand.band);
    setzeBndTitel(zustand.modell, zustand.band);
  }
  /* Ohne Leser-Wunsch gilt das Startgeraet dieses Reiters auch fuer
     „Ohne Vertrag“ - beide Reiter oeffnen mit demselben Geraet. */
  if (TR_LESER_MODELL && !(daten.erlaubt[TR_LESER_MODELL] || []).length) {
    /* Unbekannte ids zaehlen nicht als Wunsch: nur ein Geraet, das
       „Ohne Vertrag“ kennt, bleibt dort stehen. */
    var vlKnoten = document.getElementById('gr-verlaufdaten');
    var bekannt = false;
    try {
      bekannt = JSON.parse(vlKnoten ? vlKnoten.textContent : '[]')
        .some(function (g) { return g.id === TR_LESER_MODELL; });
    } catch (e) { /* kein Verlauf: nicht bekannt */ }
    if (!bekannt) TR_LESER_MODELL = null;
  }
  if (!TR_LESER_MODELL) TR_LESER_MODELL = zustand.modell;
})();
/* Die Alarmtabelle: Filter, Suche, Zeilenaufklapper, "alle anzeigen".
 *
 * Der Aufklapper einer ausgeblendeten Zeile geht mit; sonst haengt eine
 * Anbieterliste unter einer Zeile, die nicht mehr da ist. Dieselbe Falle
 * wie beim alten Vergleichsfilter, nur an einer neuen Stelle.
 */
/* Seit dem 30.08.2026 traegt diese Mechanik ZWEI Tabellen: die Alarme in
 * Reiter 1 und den flachen Katalog in Reiter 2. Beide haben dieselbe
 * Filterleiste und denselben "alle zeigen"-Knopf; sie unterscheiden sich nur
 * in den Spalten. Eine zweite Kopie dieser Funktion waere eine zweite Stelle,
 * an der die Kaskadenfalle mit `hidden` repariert werden muesste. */
function grFilterleiste(tafelId, mehrId) {
  var tafel = document.getElementById(tafelId);
  if (!tafel) return;
  var tabelle = tafel.querySelector('.gr-alarm');
  if (!tabelle) return;

  var felder = tafel.querySelectorAll('[data-filter]');
  var mehr = document.getElementById(mehrId);
  // Der ganze Absatz, nicht nur der Knopf: ein leeres <p> mit Rand bliebe
  // sonst als Luecke stehen, sobald der Knopf sich versteckt.
  var mehrAbsatz = mehr ? (mehr.closest('p') || mehr) : null;

  /* DER DECKEL FOLGT DEM FILTER (B2/B3, 31.08.2026 - Runde 2 der
     Zurueckweisung).

     Bis dahin klebte `gr-a-rest` an einer POSITION: einmal beim Laden aus
     der SSR-Reihenfolge gesetzt, einmal je Sortierklick neu vergeben
     (`sortiere()`), aber in BEIDEN Faellen unabhaengig davon, ob die Zeile
     an dieser Position ueberhaupt zum aktiven Filter passte. Zwei Klicks
     auf den Spaltenkopf "Zustand" (Reiter 2, Vorbelegung "neu") reichten,
     um elf nicht-passende Zeilen in den Deckel zu schieben und 348
     passende dahinter verschwinden zu lassen - derselbe Fehlertyp wie
     Commit 79085f0, nur ueber einen anderen Ausloeser.

     Jetzt zaehlt `anwenden()` NUR unter den TREFFERN: die ersten `deckel`
     Zeilen, die den aktiven Filter bestehen, bleiben sichtbar (oder alle,
     sobald "alle anzeigen" gedrueckt ist) - unabhaengig davon, an welcher
     Position sie in der aktuellen Sortierung stehen. `sortiere()` muss
     `gr-a-rest` deshalb nicht mehr selbst vergeben; sie ordnet nur noch die
     DOM-Knoten um und ruft danach `anwenden()`.

     Und der Knopf "alle N zeigen" verspricht nur noch, was er wirklich
     liefert: N ist die Zahl der TREFFER unter dem aktiven Filter, nicht die
     serverseitige Gesamtzahl - sonst versprach er bei aktivem "neu"-Filter
     "alle 360 zeigen" und lieferte 349 (B3). Die serverseitige Zahl
     (Ueberschrift, Export) bleibt unveraendert die Gesamtzahl - sie ist
     eine Aussage ueber den BESTAND, kein Versprechen ueber diese Anzeige. */
  var deckel = tabelle.querySelectorAll('.gr-a-zeile.gr-a-rest').length
             ? tabelle.querySelectorAll('.gr-a-zeile').length -
               tabelle.querySelectorAll('.gr-a-zeile.gr-a-rest').length
             : 0;

  /* P3-Fix (Sicht-Pruefung Wesentliches 1, 18.09.2026): die ANSICHT der
     Katalog-Tabelle darf keine Sortierung an einer unsichtbaren Spalte
     hinterlassen. Der Umschalter (`.gr-kansicht`, weiter oben im File)
     meldet seinen Wechsel als 'gr-ansicht'-Event; dieser Block entscheidet:

       * Kopf der neuen Ansicht sichtbar -> nichts zu tun.
       * Hauptpreisspalte (Einzelgeraepreis <-> TCO-24) -> der Kopf der
         GEMAPPTEN Spalte wird geklickt (Erstklick-Richtung, dieselbe wie
         ein Klick von Hand).
       * jede andere Spalte (Haendler/Spanne nur Barpreis, Ø/Delta nur
         TCO) hat keine Entsprechung -> zurueck auf die SERVER-Ordnung,
         die beim Laden hier einmal gesichert wird.

     `ordnungZurueck()` setzt ausserdem `data-vor`/`aria-sort` aller
     Koepfe zurueck - auch dann bleibt kein Pfeil ueber einer Spalte
     stehen, nach der niemand sortiert hat. */
  var anfangsordnung = [];
  Array.prototype.forEach.call(
      tabelle.querySelectorAll('.gr-a-zeile'), function (z) {
        anfangsordnung.push(
            {zeile: z,
             auf: document.getElementById(z.getAttribute('data-auf'))});
      });

  function ordnungZurueck() {
    var rumpf = tabelle.tBodies[0];
    if (!rumpf) return;
    Array.prototype.forEach.call(tabelle.querySelectorAll('.gr-sort'),
        function (a) {
          a.removeAttribute('data-vor');
          a.removeAttribute('aria-sort');
        });
    anfangsordnung.forEach(function (p) {
      rumpf.appendChild(p.zeile);
      if (p.auf) rumpf.appendChild(p.auf);
    });
    anwenden();
  }

  tabelle.addEventListener('gr-ansicht', function (ev) {
    var ansicht = ev.detail && ev.detail.ansicht;
    if (ansicht !== 'tco' && ansicht !== 'barpreis') return;
    var aktiv = tabelle.querySelector('thead .gr-sort[data-vor]');
    if (!aktiv) return;
    var spalte = aktiv.closest ? aktiv.closest('th') : null;
    if (spalte && !spalte.classList.contains(
            ansicht === 'tco' ? 'gr-sp--barpreis' : 'gr-sp--tco')) return;
    var ziel = {preis: 'tco', tco: 'preis'}[aktiv.getAttribute('data-sort')];
    var kopf = ziel && tabelle.querySelector(
        'thead .gr-sort[data-sort="' + ziel + '"]');
    if (kopf) kopf.click();
    else ordnungZurueck();
  });

  function anwenden() {
    var alleZeigen = tabelle.classList.contains('gr-alarm--alle');
    var wahl = {};
    var suche = '';
    Array.prototype.forEach.call(felder, function (f) {
      var name = f.getAttribute('data-filter');
      if (name === 'suche') suche = (f.value || '').trim().toLowerCase();
      else wahl[name] = f.value || '';
      // Ein aktiver Filter ist rot hinterlegt. Er veraendert, was darunter
      // steht, und das muss man sehen, ohne die Auswahl zu lesen.
      var etikett = f.closest('label');
      if (etikett && name !== 'suche') {
        etikett.classList.toggle('gr-filter--an', !!f.value);
      }
    });

    var zeilen = tabelle.querySelectorAll('.gr-a-zeile');
    var treffer = 0;   // wie viele Zeilen ueberhaupt zum Filter passen
    var sichtbar = 0;  // wie viele davon der Deckel wirklich zeigt
    for (var i = 0; i < zeilen.length; i++) {
      var z = zeilen[i];
      var passt = true;
      for (var name in wahl) {
        if (wahl[name] && z.getAttribute('data-' + name) !== wahl[name]) {
          passt = false;
        }
      }
      if (passt && suche) {
        passt = z.textContent.toLowerCase().indexOf(suche) >= 0;
      }
      var auf = document.getElementById(z.getAttribute('data-auf'));
      z.hidden = !passt;
      if (auf) auf.hidden = !passt;
      if (passt) {
        treffer++;
        // P1 (dritte Nachbesserung, 31.08.2026): eine `blockrest`-Zeile
        // (mehr als `BLOCK_SICHTBAR` Zeilen ihres eigenen Geraete-Blocks)
        // bleibt IMMER verborgen, unabhaengig vom Positionsdeckel - sie
        // zaehlt deshalb auch nicht gegen `sichtbar`. Ohne diese
        // Unterscheidung fuellte ein einzelner Block mit sieben
        // Farbvarianten desselben Geraets einen Grossteil der zwoelf
        // sichtbaren Zeilen der GANZEN Tabelle; mit ihr bleiben davon nur
        // die zwei guenstigsten je Anbieter sichtbar (siehe
        // `geraete_view._interleave_je_anbieter_im_block`), der Rest steht
        // direkt dahinter bereit, sobald "alle anzeigen" gedrueckt ist.
        var blockRest = z.getAttribute('data-blockrest') === '1';
        // Siehe Kommentar bei `var deckel` oben: der Positionsdeckel
        // zaehlt nur unter den TREFFERN, nicht nach roher Position.
        var raus = (blockRest && !alleZeigen)
                 || (deckel > 0 && !alleZeigen && sichtbar >= deckel);
        z.classList.toggle('gr-a-rest', raus);
        if (auf) auf.classList.toggle('gr-a-rest', raus);
        if (!raus) sichtbar++;
      }
      // Eine nicht-passende Zeile behaelt ihre `gr-a-rest`-Klasse
      // unveraendert - sie ist ohnehin `hidden`, und wird sie spaeter
      // wieder zum Treffer, rechnet der naechste Lauf dieser Schleife sie
      // frisch ein.
    }
    var leer = tafel.querySelector('.gr-a-leer');
    if (leer) leer.hidden = sichtbar > 0;

    if (mehrAbsatz) {
      mehrAbsatz.hidden = alleZeigen || treffer <= deckel;
      if (mehr) mehr.textContent = 'alle ' + treffer + ' Zeilen zeigen';
    }
  }

  Array.prototype.forEach.call(felder, function (f) {
    f.addEventListener('input', anwenden);
    f.addEventListener('change', anwenden);
  });

  // Klick auf eine Zeile klappt alle Anbieter dieses Geraets auf.
  tabelle.addEventListener('click', function (ev) {
    if (ev.target.closest('a')) return;   // der Quelllink fuehrt hinaus
    var zeile = ev.target.closest ? ev.target.closest('.gr-a-zeile') : null;
    if (!zeile) return;
    var auf = document.getElementById(zeile.getAttribute('data-auf'));
    if (auf) auf.classList.toggle('gr-a-auf--an');
  });
  tabelle.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    // B5 (31.08.2026): derselbe Ausstieg wie im `click`-Handler oben fehlte
    // hier. Ohne ihn ass `preventDefault()` das Enter eines fokussierten
    // Quelllinks: fokussierbar, aber mit der Tastatur nicht auszuloesen -
    // genau die Zugaenglichkeit, mit der B7 begruendet wurde, und B7
    // vergroessert die betroffene Flaeche vom 5-px-Pfeil auf den ganzen
    // Namen.
    if (ev.target.closest('a')) return;
    var zeile = ev.target.closest ? ev.target.closest('.gr-a-zeile') : null;
    if (!zeile) return;
    ev.preventDefault();
    var auf = document.getElementById(zeile.getAttribute('data-auf'));
    if (auf) auf.classList.toggle('gr-a-auf--an');
  });

  /* SORTIEREN NACH SPALTE.

     Zwei Dinge, die hier leicht falsch gehen, und beide sind gemeint:

     1. EINE ZEILE IST ZWEI ZEILEN. Zu jeder `.gr-a-zeile` gehoert ein
        `.gr-a-auf` mit der Anbieterliste. Verschoben werden sie IMMER
        zusammen - sonst haengt eine Anbieterliste unter einem fremden
        Geraet, und zwar ohne dass es auffiele, solange sie zugeklappt ist.

     2. SORTIERT WIRD NACH DEM ROHWERT, nicht nach dem Zelltext. "1.099,90 €"
        ist als Zeichenkette kleiner als "199,00 €"; ein Sortierer, der die
        Zelle liest, stellt den teuersten Preis nach vorn und sieht dabei
        richtig aus.

     Der DECKEL wird hier NICHT mehr vergeben (B2, 31.08.2026) - das
     erledigt `anwenden()` am Ende dieser Funktion, filterbewusst statt
     positionsbewusst. Diese Funktion ordnet nur noch die DOM-Knoten um. */
  var koepfe = tabelle.querySelectorAll('.gr-sort');

  function sortiere(schluessel, art, richtung) {
    var rumpf = tabelle.tBodies[0];
    if (!rumpf) return;
    var paare = [];
    Array.prototype.forEach.call(
      tabelle.querySelectorAll('.gr-a-zeile'), function (z) {
        paare.push({ zeile: z, wert: z.getAttribute('data-s-' + schluessel) || '',
                     auf: document.getElementById(z.getAttribute('data-auf')) });
      });
    var vz = richtung === 'ab' ? -1 : 1;
    paare.sort(function (a, b) {
      if (art === 'zahl') {
        var x = parseFloat(a.wert), yy = parseFloat(b.wert);
        /* P3 (17.09.2026): eine Zeile OHNE Wert in dieser Spalte faellt
           ans ENDE - in BEIDEN Richtungen. Bis hierhin wurde NaN zu
           -Infinity, und eine wertlose Zeile stand bei AUFSTEIGENDER
           Sortierung ganz OBEN (der Kommentar des Wahrheitstests
           `test_die_spaltenkoepfe_sind_sortierbar` beschreibt genau
           diese Luecke). Der Katalog der Modell-Ebene hat sie regulaer:
           62 Modelle ohne wesentliche Spanne, 19 ohne Bündel - das sind
           benannte Leerzustaende, keine Extremwerte, und gehoeren unter
           die Zeilen mit Zahl, nicht ueber sie. */
        var ax = isNaN(x), ay = isNaN(yy);
        if (ax || ay) {
          if (ax && ay) return 0;
          return ax ? 1 : -1;
        }
        if (x !== yy) return (x - yy) * vz;
        return 0;
      }
      return a.wert.localeCompare(b.wert, 'de') * vz;
    });
    paare.forEach(function (p) {
      rumpf.appendChild(p.zeile);
      if (p.auf) rumpf.appendChild(p.auf);
    });
    anwenden();
  }

  Array.prototype.forEach.call(koepfe, function (k) {
    k.addEventListener('click', function () {
      var schluessel = k.getAttribute('data-sort');
      var art = k.getAttribute('data-art') || 'text';
      // Erster Klick auf eine Zahlenspalte sortiert ABSTEIGEND: wer auf
      // "Unterschied" klickt, will den groessten sehen, nicht den kleinsten.
      // Bei Text ist es umgekehrt.
      var vorher = k.getAttribute('data-vor');
      var richtung;
      if (vorher === 'ab') richtung = 'auf';
      else if (vorher === 'auf') richtung = 'ab';
      else richtung = (art === 'zahl') ? 'ab' : 'auf';
      Array.prototype.forEach.call(koepfe, function (a) {
        a.removeAttribute('data-vor');
        a.removeAttribute('aria-sort');
      });
      k.setAttribute('data-vor', richtung);
      k.setAttribute('aria-sort',
                     richtung === 'ab' ? 'descending' : 'ascending');
      sortiere(schluessel, art, richtung);
    });
  });

  // Einmal beim Laden. Manche Browser stellen Formularwerte beim Reload
  // wieder her; ohne diesen Aufruf zeigt die Tabelle dann ungefiltert an,
  // was das Auswahlfeld daneben nicht sagt.
  anwenden();

  if (mehr) {
    mehr.addEventListener('click', function () {
      tabelle.classList.add('gr-alarm--alle');
      anwenden();
    });
  }
}

/* O2 (11.09.2026): die Alarmtabelle lebt auf dem WETTBEWERBS-RADAR
   (#wr-alarme) - dieselbe Mechanik (Filter, Suche, Sortierung, Deckel,
   Aufklapper), derselbe Initialisierer, nur ein anderer Behaelter. Auf
   geraete.html existiert #wr-alarme nicht, der Aufruf kehrt sofort
   zurueck (Guard am Funktionskopf). */
grFilterleiste('wr-alarme', 'gr-mehr');
grFilterleiste('tafel-katalog', 'gr-kmehr');
/* E3/S2: die MODELL-LISTE im Radar-Reiter (#wr-abweichung) - dieselbe
 * Mechanik (Sortierung nach Rohwert, Deckel, Aufklappzeilen), derselbe
 * Initialisierer. Auf der Schwesterseite existiert der Container nicht,
 * der Aufruf kehrt sofort zurueck (Guard am Funktionskopf).
 *
 * #wr-alarme steht seit E3 AUCH im Radar-Reiter von geraete.html (neben
 * der Schwesterseite) - der Aufruf darueber ist unveraendert; die IDs
 * gr-mehr/gr-wmehr sind je Seite eindeutig (der Katalog nutzt gr-kmehr). */
grFilterleiste('wr-abweichung', 'gr-wmehr');

/* =========================================================================
   NEWSLETTER-ANMELDUNG
   =========================================================================
   Drei Dinge passieren hier, und das erste ist das, das man leicht vergisst.

   1. `GET /form-token` wird beim SEITENAUFBAU geholt, nicht beim Absenden.
      Render Free faehrt den Signup-Dienst nach 15 Minuten ohne Verkehr
      herunter, das Aufwachen dauert rund eine Minute. Wer die Kennung erst
      beim Klick holt, laesst den Nutzer diese Minute vor einem Spinner
      warten. Geholt beim Aufbau, weckt sie die Instanz, waehrend er noch
      ausfuellt.
   2. Die Stichwort-Vorschau zaehlt CLIENTSEITIG gegen
      `data/keyword-index.json`. Sie kann `preview_keyword` nicht aufrufen -
      die Seite ist statisch, und der Signup-Dienst kennt die Berichtsarchive
      nicht. Die Datei schreibt die Pipeline bei jedem Lauf mit, und ein Test
      haelt jedes ihrer Woerter gegen `vorschau()`.
   3. Der Kaltstart wird trotzdem abgefangen: sofort "Wird verarbeitet ...",
      Timeout 90 Sekunden, danach eine verstaendliche Meldung mit
      Wiederholmoeglichkeit. Kein haengender Spinner.
   ====================================================================== */
(function () {
  var form = document.getElementById('nl-form');
  if (!form) return;
  var konfigEl = document.getElementById('nl-config');
  var K = {};
  try { K = JSON.parse(konfigEl ? konfigEl.textContent : '{}'); } catch (e) {}

  var status = document.getElementById('nl-status');
  var submit = document.getElementById('nl-submit');
  var gesperrt = form.getAttribute('data-gesperrt') === '1' || !K.frei || !K.dienst;
  var nonce = '';
  var stichwoerter = [];
  var index = null;

  function sagen(text, art) {
    status.textContent = text || '';
    status.className = 'nl-status' + (art ? ' nl-status--' + art : '');
  }

  /* ---- 1. Die Kennung beim Seitenaufbau holen. Weckt die Instanz. ---- */
  if (!gesperrt) {
    fetch(K.dienst + '/form-token', { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.nonce) nonce = d.nonce; })
      .catch(function () { /* still: der Absendeweg faengt es ab */ });
  } else if (K.frei && !K.dienst) {
    sagen('Der Anmeldedienst ist noch nicht eingerichtet.', 'warn');
  }

  /* ---- Regionen und Themen gelten nur fuer Meldungen: ausgeblendet und
     geleert, sobald Bereiche ohne Meldungen gewaehlt sind. ------------- */
  function nurMeldungenZeigen() {
    var bereiche = gewaehlt('branches');
    var an = !bereiche.length || bereiche.indexOf(K.meldungen) >= 0;
    form.querySelectorAll('[data-nur-meldungen]').forEach(function (block) {
      block.hidden = !an;
      if (!an) block.querySelectorAll('input').forEach(function (el) { el.checked = false; });
    });
  }
  form.querySelectorAll('input[name="branches"]').forEach(function (el) {
    el.addEventListener('change', nurMeldungenZeigen);
  });

  /* ---- 2. Stichwoerter: Vorschau gegen den Index ---------------------- */
  function indexLaden() {
    if (index) return Promise.resolve(index);
    return fetch('data/keyword-index.json')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { index = d || { woerter: {}, meldungen: 0 }; return index; })
      .catch(function () { index = { woerter: {}, meldungen: 0 }; return index; });
  }

  /* Dieselbe Rechnung wie `filters.vorschau()`: gezaehlt werden MELDUNGEN,
     die das Wort enthalten, nicht Vorkommen. Fuer eine Phrase laesst sich
     das aus einem Wortindex nur nach oben abschaetzen - dann sagt die
     Vorschau "höchstens N" und behauptet keine Zahl, die sie nicht hat. */
  function schaetzen(term) {
    var teile = term.toLowerCase().split(/\s+/).filter(function (w) {
      return w.length >= (K.min_laenge || 4);
    });
    if (!teile.length) return null;
    var werte = teile.map(function (w) { return index.woerter[w] || 0; });
    var n = Math.min.apply(null, werte);
    return { n: n, genau: teile.length === 1 };
  }

  var feld = document.getElementById('nl-stichwort');
  var vorschau = document.getElementById('nl-stichwort-vorschau');
  var liste = document.getElementById('nl-stichwort-liste');

  function vorschauZeigen() {
    var term = (feld.value || '').trim();
    if (term.length < (K.min_laenge || 4)) { vorschau.textContent = ''; return; }
    indexLaden().then(function () {
      var s = schaetzen(term);
      if (!s) { vorschau.textContent = ''; return; }
      var tage = K.vorschau_tage || 30;
      vorschau.textContent = (s.genau ? '' : 'höchstens ') + s.n +
        ' Meldung' + (s.n === 1 ? '' : 'en') + ' in den letzten ' + tage + ' Tagen';
      vorschau.className = 'nl-vorschau' +
        (s.n >= (K.warnung_ab || 25) ? ' nl-vorschau--warn' : '') +
        (s.n === 0 ? ' nl-vorschau--null' : '');
      if (s.n >= (K.warnung_ab || 25)) {
        vorschau.textContent += ' — das ist viel. Enger fassen?';
      } else if (s.n === 0) {
        vorschau.textContent += ' — dazu kam bisher nichts.';
      }
    });
  }

  feld.addEventListener('input', vorschauZeigen);

  function chipsZeichnen() {
    liste.textContent = '';
    stichwoerter.forEach(function (term, i) {
      var li = document.createElement('li');
      li.className = 'nl-chip';
      li.appendChild(document.createTextNode(term));
      var weg = document.createElement('button');
      weg.type = 'button';
      weg.className = 'nl-chip-weg';
      weg.textContent = '×';
      weg.setAttribute('aria-label', 'Stichwort ' + term + ' entfernen');
      weg.addEventListener('click', function () {
        stichwoerter.splice(i, 1);
        chipsZeichnen();
      });
      li.appendChild(weg);
      liste.appendChild(li);
    });
  }

  document.getElementById('nl-stichwort-add').addEventListener('click', function () {
    var term = (feld.value || '').trim();
    var min = K.min_laenge || 4;
    var laengstes = term.split(/\s+/).reduce(function (a, w) {
      return Math.max(a, w.length);
    }, 0);
    if (laengstes < min) {
      sagen('Stichwörter brauchen mindestens ein Wort mit ' + min +
            ' Zeichen — kurze Begriffe treffen zu viel.', 'warn');
      return;
    }
    if (stichwoerter.length >= (K.max_stichwoerter || 10)) {
      sagen('Höchstens ' + (K.max_stichwoerter || 10) + ' Stichwörter.', 'warn');
      return;
    }
    if (stichwoerter.indexOf(term) < 0) stichwoerter.push(term);
    feld.value = '';
    vorschau.textContent = '';
    sagen('');
    chipsZeichnen();
  });

  feld.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      document.getElementById('nl-stichwort-add').click();
    }
  });

  /* ---- 3. Absenden, mit Kaltstart-Behandlung -------------------------- */
  function gewaehlt(feldName) {
    return Array.prototype.slice.call(
      form.querySelectorAll('input[name="' + feldName + '"]:checked')
    ).map(function (el) { return el.value; });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (gesperrt) {
      sagen('Die Anmeldung ist noch nicht freigeschaltet.', 'warn');
      return;
    }
    var email = (document.getElementById('nl-email').value || '').trim();
    if (!email || email.indexOf('@') < 1) {
      sagen('Bitte eine gültige E-Mail-Adresse eintragen.', 'warn');
      return;
    }
    if (!document.getElementById('nl-consent').checked) {
      sagen('Ohne Ihr Häkchen bei der Einwilligung geht es nicht.', 'warn');
      return;
    }

    var koerper = {
      email: email,
      nonce: nonce,
      consent: true,
      website: (form.querySelector('input[name="website"]') || {}).value || '',
      filters: {
        branches: gewaehlt('branches'),
        regions: gewaehlt('regions'),
        competitors: gewaehlt('competitors'),
        categories: gewaehlt('categories'),
        keywords: stichwoerter.map(function (t) { return { term: t }; })
      }
    };

    submit.disabled = true;
    sagen('Wird verarbeitet …');

    /* 90 Sekunden. Der Kaltstart dauert rund eine Minute, und der Nutzer
       soll danach eine Antwort bekommen - keinen ewigen Spinner. */
    var abbruch = new AbortController();
    var uhr = setTimeout(function () { abbruch.abort(); }, 90000);

    fetch(K.dienst + '/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(koerper),
      signal: abbruch.signal
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, daten: d }; });
    }).then(function (a) {
      clearTimeout(uhr);
      submit.disabled = false;
      if (a.ok) {
        sagen(a.daten.message || 'Bitte sehen Sie in Ihr Postfach.', 'ok');
        form.querySelector('#nl-email').value = '';
        document.getElementById('nl-consent').checked = false;
      } else {
        sagen((a.daten.fehler || ['Das hat nicht geklappt.']).join(' '), 'warn');
      }
    }).catch(function (err) {
      clearTimeout(uhr);
      submit.disabled = false;
      /* Der Dienst schlaeft nach 15 Minuten ohne Verkehr ein. Das ist der
         haeufigste Fall hier - und er ist beim zweiten Versuch weg. */
      sagen(err && err.name === 'AbortError'
        ? 'Der Anmeldedienst antwortet gerade nicht (er wacht nach einer '
          + 'Pause erst auf). Bitte noch einmal auf „Anmelden“ klicken.'
        : 'Verbindung zum Anmeldedienst fehlgeschlagen. Bitte später noch '
          + 'einmal versuchen.', 'warn');
    });
  });
})();

/* ===================================================================
   Geraeteradar, Reiter 3: der Preisverlauf EINES Geraets.

   Das einzige Diagramm der Seite. Es entsteht erst nach einer Auswahl -
   ohne Auswahl steht dort ein Satz und KEIN leeres SVG, weil ein leerer
   Rahmen so aussieht, als seien die Daten weg.

   Gezeichnet wird von Hand: reines SVG, keine Bibliothek, kein CDN. Die
   Reihen kommen fertig gerechnet aus `report/geraete_verlauf.py`; hier
   passiert nur Geometrie.

   DIE ZWEI HARTEN GRENZEN, beide aus dem Auftrag und beide der Grund,
   warum diese Achse lesbar ist, wo die geloeschte Grafik es nicht war:
   hoechstens acht Linien (das rechnet das Python-Modul) und hoechstens
   acht WAAGERECHTE Datumsbeschriftungen (das rechnet `beschriftung()`).
   Weitere Messpunkte werden gezeichnet, nur nicht beschriftet. Kein
   gedrehter Text, keine Schrift unter 12 px, nichts mit "..." gekuerzt.
   =================================================================== */
(function () {
  var daten = document.getElementById('gr-verlaufdaten');
  var feld = document.getElementById('gr-vsuche');
  if (!daten || !feld) return;

  var GERAETE = [];
  try { GERAETE = JSON.parse(daten.textContent) || []; } catch (e) { return; }
  if (!GERAETE.length) return;

  var NS = 'http://www.w3.org/2000/svg';
  /* K (QA-Fix 24.09.2026): BREITE/HOEHE sind ab jetzt die GEMESSENE
     Containerbreite in CSS-Pixeln, nicht mehr eine feste Zeichenflaeche,
     die der Browser per `viewBox` auf die Containerbreite HERUNTERSKALIERT.
     Bei einer festen `BREITE=1080` und `width:100%` skalierte das ganze
     Koordinatensystem samt Schrift mit - am Telefon (~340 px Container)
     blieben von 12 px Schrift rund 3,8 px uebrig, unlesbar. `zeichne()`
     setzt beide Werte bei JEDEM Aufruf aus der REALEN Breite von `#gr-
     vbild` neu (siehe dort); die BASIS-Werte bleiben nur der Startwert
     UND das Seitenverhaeltnis (HOEHE_BASIS/BREITE_BASIS), mit dem HOEHE
     aus der gemessenen Breite folgt. */
  var BREITE_BASIS = 1080, HOEHE_BASIS = 340;
  var BREITE = BREITE_BASIS, HOEHE = HOEHE_BASIS;
  var RAND = { oben: 18, rechts: 20, unten: 46, links: 74 };
  var MAX_MARKEN = 8;
  /* K: derselbe rechte Rand wie `ENDLABEL_RAND` im Server-Chart
     (`geraete_zeitreihe.py`) fuer das Verdeckt-Endlabel weiter unten. */
  var ENDLABEL_RAND = 6;
  /* M: senkrechter Abstand des Verdeckt-Endlabels zu SEINER eigenen
     Linie/seinem Punkt (die auf derselben Hoehe y(preis) liegen) - siehe
     `endlabelListe` in `zeichne()`. */
  var ENDLABEL_Y_VERSATZ = 22;

  var treffer = document.getElementById('gr-vtreffer');
  var steuer = document.getElementById('gr-vsteuer');
  var kacheln = document.getElementById('gr-vkacheln');
  var leer = document.getElementById('gr-vleer');
  var bild = document.getElementById('gr-vbild');
  var legende = document.getElementById('gr-vlegende');
  var tabelle = document.getElementById('gr-vtabelle');
  var zukurz = document.getElementById('gr-vzukurz');
  var stand = document.getElementById('gr-vstand');
  /* Die zwei Schwellen kommen aus `report/geraete_verlauf.py` und stehen als
     data-Attribute am Satz. Sie hier zu wiederholen waeren zwei Zahlen fuer
     dieselbe Regel - genau der Fehler, den CLAUDE.md 6 fuer die
     Stichwort-Vorschau beschreibt. */
  var AB_TERMINEN = parseInt((stand && stand.dataset.abterminen) || '4', 10);
  /* Zwei Linien, die naeher als das beieinander liegen, sind im Bild eine.
     Anteil der gezeichneten Preisspanne, nicht Euro: 90 Cent sind bei einer
     Spanne von 307 Euro unsichtbar und bei einer von 5 Euro deutlich.

     AUS DEM MODUL, nicht hier hartkodiert. Die erste Fassung schrieb 0.02
     an beide Stellen - `geraete_verlauf.LINIEN_ABSTAND` reiste in den
     View-Dict und wurde von niemandem gelesen. Wer die Python-Konstante
     geaendert haette, haette die Seite nicht geaendert; genau die
     Fehlerklasse, die der Kommentar zu AB_TERMINEN zwei Zeilen weiter oben
     vermeidet (CLAUDE.md §6, Stichwort-Vorschau). */
  var ABSTAND = parseFloat((stand && stand.dataset.abstand) || '0.02');
  /* A/E (QA-Fix 24.09.2026): dieselbe Messluecken-Schwelle wie der
     TCO-Server-Chart (`geraete_zeitreihe.LUECKE_TAGE_SCHWELLE`) - aus
     `report/geraete_verlauf.py` durchgereicht, NICHT hier hartkodiert
     (derselbe Grund wie AB_TERMINEN/ABSTAND zwei Zeilen oben). KEIN
     Rueckfall-Literal: fehlt das Attribut, bleibt LUECKE_TAGE NaN. Jeder
     Vergleich `tage > NaN` ist dann false - keine Zeile gilt je als
     Luecke, statt eine geratene Schwelle zu benutzen (CLAUDE.md
     "Clean Code" 3: ein fehlender Wert ist eine benannte Luecke, nie ein
     geratener Wert). */
  var LUECKE_TAGE = stand && stand.dataset.lueckeTage
    ? parseInt(stand.dataset.lueckeTage, 10)
    : (console.error(
        'gr-vstand: data-luecke-tage fehlt - Messluecken werden nicht ' +
        'erkannt statt mit einer geratenen Schwelle gerechnet.'), NaN);
  /* I2 (QA-Fix 24.09.2026): AB WIE VIELEN MESSTERMINEN DER SATZ SCHWEIGT.
     Aus `report/geraete_verlauf.py` (`VERLAUF_SATZ_MAX_TERMINE`), nicht
     hier hartkodiert - derselbe Grund wie bei AB_TERMINEN/ABSTAND/
     LUECKE_TAGE. Unterhalb der Schwelle nennt der Satz eine Auskunft, die
     die Kachel "Messtermine" nicht hat (die SPANNE, "vom … bis zum …");
     darueber doppelt er nur noch deren Zahl. KEIN Rueckfall-Literal:
     fehlt das Attribut, schweigt der Satz ganz (siehe `satz()`) statt
     mit einer geratenen Schwelle zu erscheinen. */
  var SATZ_MAX_TERMINE = stand && stand.dataset.satzmaxtermine
    ? parseInt(stand.dataset.satzmaxtermine, 10)
    : (console.error(
        'gr-vstand: data-satzmaxtermine fehlt - der Stand-Satz bleibt ' +
        'stumm statt mit einer geratenen Schwelle zu erscheinen.'), NaN);
  /* H2 (QA-Fix 24.09.2026): Mindestabstand zweier X-Achsen-Beschriftungen
     im SVG-Koordinatensystem (1080 breit) - siehe `xMarkenOhneUeberlappung`
     weiter unten. */
  var X_MARKEN_LUECKE = 6;
  var von = document.getElementById('gr-vvon');
  var bis = document.getElementById('gr-vbis');
  var gewaehlt = null, raster = 'woche';

  function euro(n) {
    return n.toLocaleString('de-DE', { minimumFractionDigits: 2,
                                       maximumFractionDigits: 2 }) + ' €';
  }
  function tagDE(iso) {
    var t = iso.split('-');
    return t[2].replace(/^0/, '') + '.' + t[1].replace(/^0/, '') + '.';
  }
  var MONATE = ['Jan','Feb','Mär','Apr','Mai','Jun',
                'Jul','Aug','Sep','Okt','Nov','Dez'];
  /* Die Beschriftung nennt, was das Raster ZUSAMMENFASST. Eine
     "Quartal"-Ansicht mit zwei Tagesmarken behauptet eine Genauigkeit, die
     sie gerade weggerechnet hat. */
  function markeDE(iso, wie) {
    var t = iso.split('-');
    if (wie === 'monat') return MONATE[parseInt(t[1], 10) - 1] + ' ' + t[0];
    if (wie === 'quartal') {
      return 'Q' + Math.ceil(parseInt(t[1], 10) / 3) + ' ' + t[0];
    }
    return tagDE(iso);
  }
  /* Tage seit einem festen Nullpunkt - ohne `new Date()`, damit die Rechnung
     nicht an der Zeitzone des Lesers haengt. */
  function tagNr(iso) {
    var t = iso.split('-').map(Number);
    var a = (t[0] * 12 + (t[1] - 1)) / 12;
    return Math.floor(a * 365.2425) + t[2];
  }

  /* Welche Tage eine Beschriftung bekommen.

     Nie mehr als MAX_MARKEN, und immer der erste und der letzte - eine
     Achse, deren Enden unbeschriftet sind, sagt nicht, welchen Zeitraum
     sie zeigt. Dazwischen wird gleichmaessig ausgeduennt. */
  function beschriftung(tage) {
    if (tage.length <= MAX_MARKEN) return tage.slice();
    var schritt = (tage.length - 1) / (MAX_MARKEN - 1), raus = [];
    for (var i = 0; i < MAX_MARKEN; i++) raus.push(tage[Math.round(i * schritt)]);
    return raus.filter(function (t, i, a) { return a.indexOf(t) === i; });
  }

  /* Die Reihe auf das gewaehlte Raster zusammenfassen.

     Je Zeitfenster bleibt der LETZTE Messpunkt stehen, nicht der
     Mittelwert: ein Mittelwert aus zwei Preisen ist ein Preis, den nie
     jemand verlangt hat. */
  function fassen(punkte, wie) {
    var je = {};
    punkte.forEach(function (p) {
      var t = p.datum.split('-');
      var k;
      if (wie === 'monat') { k = t[0] + '-' + t[1]; }
      else if (wie === 'quartal') {
        k = t[0] + '-Q' + Math.ceil(parseInt(t[1], 10) / 3);
      } else {
        // Woechentlich hiess bis zum 30.08.2026 "gar nicht" - der Knopf gab
        // die Punkte unveraendert zurueck und zeigte damit Rohtage. Jetzt
        // fasst er wirklich je Kalenderwoche zusammen (Montag als Anker,
        // ohne `new Date()`).
        k = String(Math.floor(tagNr(p.datum) / 7));
      }
      if (!je[k] || p.datum > je[k].datum) je[k] = p;
    });
    return Object.keys(je).map(function (k) { return je[k]; })
      .sort(function (a, b) { return a.datum < b.datum ? -1 : 1; });
  }

  function el(name, attrs, text) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) if (attrs[k] !== null) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /* EINE ZAHL ZUR ZEIT - und zwar DIESES Geraets.

     Der Satz unter dem Diagramm spricht seit P2 nur noch ueber das
     gewaehlte Geraet ("liegen 11 Messtermine vor"). Bis P2 trug er ohne
     Auswahl zusaechlich den globalen Stand ("seit dem 10. August, 20
     Messtermine") samt Nachsatz zur Belastbarkeit - am 30.08.2026 standen
     Kachel (4) und Satz (5) mit zwei richtigen Zahlen fuer scheinbar
     dieselbe Sache nebeneinander. Die globalen Zahlen stehen seit
     28.09.2026 nicht mehr auf der Seite (Datenlage-Aufklapper gefallen);
     der dynamische Satz hier gehoert ganz dem gezeichneten Geraet. */
  function termine(n) {
    return n === 1 ? 'liegt 1 Messtermin' : 'liegen ' + n + ' Messtermine';
  }
  /* EINE MESSLUECKE WIRD BENANNT (QA-Befund B2). Die Tage mit zwei Preisen
     derselben Listung fehlen in den Reihen - `geraete_verlauf.messtage` hat
     sie herausgenommen -, und ohne diesen Satz laese sich die Luecke als
     "unveraendert". */
  function mehrdeutigSatz(g) {
    if (!g || !g.mehrdeutig || !g.mehrdeutig.length) return '';
    return g.mehrdeutig.map(function (m) {
      var n = m.tage.length;
      return ' ' + m.anbieter + ' nannte an ' + n +
        (n === 1 ? ' Messtag' : ' Messtagen') +
        ' zwei Preise derselben Listung – diese Tage sind als Messlücke ' +
        'ausgelassen, nicht als Preisänderung gezählt.';
    }).join('');
  }
  /* `tagDE` endet auf einem Punkt ("30.8."). Ein Satzpunkt dahinter ergibt
     "30.8.." - im ersten Anlauf genau so auf der Seite gestanden, an ZWEI
     Stellen. Deshalb setzt `punkt()` das Satzende, nicht der Aufrufer. */
  function spanne(tage) {
    return 'vom ' + tagDE(tage[0]) + ' bis zum ' + tagDE(tage[tage.length - 1]);
  }
  function punkt(text) {
    return text.charAt(text.length - 1) === '.' ? text : text + '.';
  }

  function satzFuer(g, tage, gezeichnet) {
    if (!stand) return;
    /* OHNE GEWAEHLTES GERAET SCHWEIGT DIESER SATZ. Der Zustand entsteht
       seit der Auto-Vorauswahl nur noch beim Rueckbau (der Leser tippt im
       Suchfeld) - ein Satz ueber kein Geraet waere keine Auskunft. */
    if (!g || !tage || !tage.length) {
      stand.hidden = true;
      /* P4-Fix (Code-Pruefung 18.09., S2): ohne gewaehltes Geraet muss
         auch die LEITZAHL weg. Beide Rueckbau-Pfade (leeres Zeitfenster
         in `zeichne`, Suchfeld-Input) laufen HIER zusammen - vorher blieb
         #gr-vleit mit dem Preis des VORHERIGEN Zustands stehen, waehrend
         die Tafel daneben "Kein Geraet gefunden." sagte. Die groesste
         Zahl der Tafel darf keine Zahl behaupten, die Tafel gar nicht
         mehr hat. Der Gatter-Fall (kurze Reihe) versteckt sie NICHT -
         dort ist die Leitzahl gerade die wichtigste Auskunft. */
      var leitWeg = document.getElementById('gr-vleit');
      if (leitWeg) leitWeg.hidden = true;
      return;
    }
    /* UNTER DEM GATTER SCHWEIGT DIESER SATZ. Der Hinweis an der Stelle des
       Diagramms sagt dann dasselbe, und zwar dort, wo die Frage entsteht -
       beide zusammen waeren dieselbe Zahl zweimal auf einem Bildschirm,
       genau die Beruhigungsregel aus CLAUDE.md 5. */
    if (tage.length < AB_TERMINEN || gezeichnet < AB_TERMINEN) {
      stand.hidden = true; return;
    }
    /* I2: AB SATZ_MAX_TERMINE SCHWEIGT DER SATZ AUCH HIER - er doppelte
       sonst wortgleich die Kachel "Messtermine" (QA-Befund, 24.09.2026:
       "liegen 16 Messtermine vor" stand neben einer Kachel, die dieselbe
       16 schon zeigte, ohne neue Auskunft ausser der Spanne). Unterhalb
       der Schwelle bleibt er stehen - dort ist die Spanne selbst eine
       Auskunft ueber eine noch duenne Datenlage. */
    /* Fehlt die Schwelle (data-satzmaxtermine, siehe oben), ist der
       Vergleich `> NaN` immer false und der Satz erschiene ungeprueft -
       darum hier die eigene, benannte Ausfallpruefung statt eines
       geratenen Werts. */
    if (isNaN(SATZ_MAX_TERMINE) || tage.length > SATZ_MAX_TERMINE) {
      stand.hidden = true; return;
    }
    stand.hidden = false;
    stand.textContent = punkt('Für dieses Gerät ' + termine(tage.length) +
      ' vor, ' + spanne(tage)) + mehrdeutigSatz(g);
  }

  function zeichne(g) {
    /* K: BREITE AUS DEM CONTAINER MESSEN - VOR jeder anderen Rechnung,
       denn `x()`/`y()`/die viewBox haengen daran. Ist `#gr-vbild` gerade
       verborgen (Reiterwechsel `display:none`, `.gr-tafel--aus`), liefert
       `getBoundingClientRect()` eine Breite von 0 - kein falscher Wert,
       nur unbrauchbar; dann bleibt die BASIS-Breite der Startwert, und
       der Redraw beim Sichtbarwerden (`gr-tafel-sichtbar`, siehe unten)
       holt die echte Zahl nach. */
    var gemessen = bild ? Math.round(bild.getBoundingClientRect().width) : 0;
    BREITE = gemessen > 0 ? gemessen : BREITE_BASIS;
    /* HOEHE BLEIBT FEST, SKALIERT NICHT MIT DER BREITE. Ein Seiten-
       verhaeltnis wie bei der Desktop-Flaeche (1080x340) haette am
       Telefon (~306 px breit) nur 96 px Hoehe gelassen - die absoluten
       Raender (RAND.oben/unten: 18/46 px) und vier Preis-Hilfslinien
       passen in 96 px nicht auseinandergehalten hinein, selbst bei
       echten 12 px Schrift wirkte das Bild dadurch gestaucht und
       unlesbar (QA-Fix 24.09.2026, zweiter Befund). Die senkrechte
       Zeichenflaeche bleibt darum bei JEDER Breite `HOEHE_BASIS` - nur
       die Breite ist responsiv, die Hoehe des Diagramms nicht. */
    HOEHE = HOEHE_BASIS;
    var vonT = von.value, bisT = bis.value;
    /* EIN MESSTERMIN IST EIN TAG, AN DEM GEMESSEN WURDE - unabhaengig
       davon, welches Raster gerade gewaehlt ist.

       Die erste Fassung zaehlte die Termine NACH `fassen()`, also die
       gefuellten Zeitfenster. Beim Galaxy S25 128 GB standen damit "3
       Messtermine" an der Kachel, obwohl an vier Tagen gemessen wurde -
       zwei davon lagen in derselben Kalenderwoche. Der Umschalter
       "Woechentlich/Monatlich" haette so die Zahl der Messungen veraendert,
       und im Quartalsraster haette JEDES Geraet genau einen Termin gehabt.

       Das Raster formt die LINIE, es formt nicht die Datenlage. Kachel,
       Gatter und Satz rechnen deshalb auf `rohTage`; nur die Achse rechnet
       auf den zusammengefassten Punkten. */
    var gefiltert = g.reihen.map(function (r) {
      return { anbieter: r.anbieter, farbe: r.farbe, eigen: r.eigen,
               slug: r.slug,
               roh: r.punkte.filter(function (p) {
                 return (!vonT || p.datum >= vonT) && (!bisT || p.datum <= bisT);
               }) };
    });
    var rohMenge = {};
    gefiltert.forEach(function (r) {
      r.roh.forEach(function (p) { rohMenge[p.datum] = 1; });
    });
    var rohTage = Object.keys(rohMenge).sort();

    var reihen = gefiltert.map(function (r) {
      return { anbieter: r.anbieter, farbe: r.farbe, eigen: r.eigen,
               slug: r.slug, punkte: fassen(r.roh, raster) };
    }).filter(function (r) { return r.punkte.length; });

    bild.innerHTML = '';
    legende.innerHTML = '';
    tabelle.innerHTML = '';
    if (zukurz) { zukurz.hidden = true; zukurz.textContent = ''; }
    if (!reihen.length) {
      leer.hidden = false;
      leer.textContent = 'Für diesen Zeitraum liegen keine Messpunkte vor.';
      bild.hidden = true; legende.hidden = true; tabelle.hidden = true;
      kacheln.hidden = true;
      // Sonst behaelt der Satz die Zahlen des letzten Zustands, waehrend
      // daneben steht, dass es keine Messpunkte gibt.
      satzFuer(null, null, 0);
      return;
    }
    leer.hidden = true;
    tabelle.hidden = false;
    kacheln.hidden = false;

    var alle = [], tage = {};
    reihen.forEach(function (r) {
      r.punkte.forEach(function (p) { alle.push(p.preis); tage[p.datum] = 1; });
    });
    var tageSort = Object.keys(tage).sort();
    var lo = Math.min.apply(null, alle), hi = Math.max.apply(null, alle);

    /* DIE KACHELN UND DER SATZ GEHOEREN NICHT ZUM DIAGRAMM.

       Sie stehen deshalb hier, vor dem Gatter darunter: auch ein Geraet mit
       zwei Messterminen hat einen niedrigsten und einen hoechsten Preis,
       und die Zahl seiner Termine ist gerade dann die wichtigste Auskunft
       der Seite. */
    document.getElementById('gr-vmin').textContent = euro(lo);
    document.getElementById('gr-vmax').textContent = euro(hi);
    document.getElementById('gr-vanb').textContent = reihen.length;
    /* MESSTERMINE, nicht Preispunkte - dieselbe Menge, die das Gatter zaehlt
       und die der Satz darunter nennt. Vorher stand hier `alle.length`
       (Preispunkte ueber alle Anbieter) unter der Ueberschrift
       "Messpunkte", waehrend zwei Zeilen tiefer eine andere Zahl unter
       "Messtermine" stand. */
    document.getElementById('gr-vpkt').textContent = rohTage.length;

    /* P4/D4 (18.09.2026): DIE LEITZAHL DES REITERS - der AKTUELLE Preis
       des gewaehlten Geraets, groesste Zahl der Tafel (.gr-leit-zahl).
       Gerechnet aus denselben UNGEFASSTEN Rohpunkten, die auch die
       Kacheln fuellen: der guenstigste Preis am LETZTEN Messtag einer
       jeden Reihe. Keine zweite Datenquelle, kein Rastereinfluss:
       "aktuell" ist der letzte Messpunkt, egal welches Zeitfenster die
       Kurve gerade fasst. Kacheln und Satz darunter nennen weiter
       min/max/Termine - keine Zahl doppelt. */
    var leit = document.getElementById('gr-vleit');
    if (leit) {
      var aktuell = null;
      gefiltert.forEach(function (r) {
        if (!r.roh.length) return;
        /* der SPAETESTE Punkt der Reihe (reduce statt [length-1]: die
           Sortierung der Rohpunkte ist eine Annahme des Lieferanten,
           keine dieser Stelle). */
        var p = r.roh.reduce(function (a, b) {
          return b.datum > a.datum ? b : a; });
        if (!aktuell || p.preis < aktuell.p.preis) {
          aktuell = { p: p, anbieter: r.anbieter };
        }
      });
      if (aktuell) {
        leit.hidden = false;
        document.getElementById('gr-vaktuell').textContent =
          euro(aktuell.p.preis);
        document.getElementById('gr-vleit-label').textContent =
          'aktuell · ' + (aktuell.anbieter || '') + ' · ' +
          tagDE(aktuell.p.datum);
      } else {
        leit.hidden = true;
      }
    }

    satzFuer(g, rohTage, tageSort.length);

    /* GATTER: unter AB_TERMINEN Messterminen KEIN Diagramm.

       Zwei Punkte ergeben eine Gerade, und eine Gerade durch zwei Punkte
       sieht aus wie ein Trend. Die Tabelle darunter sagt dasselbe ohne die
       Behauptung, und der Satz sagt, ab wann ein Verlauf entsteht. Ein
       leeres Bild mit Rasterlinien und Legende ist keine ehrlichere
       Darstellung derselben Lage - es ist eine unehrlichere.

       GEZAEHLT WIRD BEIDES: die Messtage (`rohTage`) UND die Punkte, die
       nach der Rasterung wirklich gezeichnet werden (`tageSort`). Der
       erste Anlauf zaehlte nur die Messtage - und damit hob der
       Rasterschalter das Gatter aus: vier Messtage im Monatsraster sind EIN
       Zeitfenster, jede Reihe hat dann genau einen Punkt, und `<path>` wird
       fuer eine Reihe mit einem Punkt gar nicht gezeichnet. Im echten
       Chromium gemessen stand dort ein "Preisverlauf" mit null Linien und
       zwei Punkten in der Bildmitte - genau das, wogegen dieses Gatter
       gebaut ist, nur eine Stufe spaeter.

       Die ZAHL im Satz bleibt die der Messtage: das Raster formt die Linie,
       nicht die Datenlage. Nur ob ueberhaupt gezeichnet wird, haengt auch
       daran, ob nach der Rasterung noch eine Linie uebrig ist. */
    if (rohTage.length < AB_TERMINEN || tageSort.length < AB_TERMINEN) {
      bild.hidden = true; legende.hidden = true;
      if (zukurz) {
        zukurz.hidden = false;
        zukurz.textContent = punkt('Für dieses Gerät ' +
          termine(rohTage.length) + ' vor, ' + spanne(rohTage)) +
          (rohTage.length >= AB_TERMINEN
            ? ' In diesem Raster fallen sie auf ' + tageSort.length +
              ' Punkt' + (tageSort.length === 1 ? '' : 'e') +
              ' zusammen – für einen Verlauf braucht es ' + AB_TERMINEN +
              /* S6: "Wöchentlich" ist das feinste Raster - der Hinweis
                 versprach dort etwas, das es nicht gibt. */
              (raster === 'woche' ? '.' : '. Ein feineres Raster zeigt mehr.')
            : ' Ein Verlauf entsteht ab ' + AB_TERMINEN + '.') +
          ' Bis dahin stehen die Preise als Tabelle darunter.' +
          mehrdeutigSatz(g);
      }
      tabelleBauen(reihen);
      return;
    }
    bild.hidden = false; legende.hidden = false;
    // EINE SPANNE VON NULL ist der Normalfall, nicht der Sonderfall: 41 der
    // 89 waehlbaren Geraete haben genau einen Preis. Die erste Fassung schob
    // dafuer `hi` auf `lo + 1` - und beschriftete die vier Hilfslinien aus
    // dem verschobenen Wert. Bei einem einzigen Preis von 999,00 EUR stand
    // dann dreimal "1000 EUR" an der Achse, ein Preis, den es im Datensatz
    // nicht gibt. Auf einer Seite, deren Leitsatz "geschaetzte Preise gibt
    // es hier nicht" lautet, ist das die teuerste Sorte falscher Zahl.
    //
    // Jetzt traegt die Achse in diesem Fall EINE Linie mit dem echten Preis,
    // und die Kurve laeuft auf halber Hoehe. `flach` ist ein eigenes Flag -
    // `hi === lo + 1` als Erkennungsmerkmal traf jede echte Spanne von genau
    // einem Euro.
    var flach = (hi === lo);
    var innenH = HOEHE - RAND.oben - RAND.unten;

    function y(preis) {
      if (flach) return RAND.oben + innenH / 2;
      return RAND.oben + innenH - ((preis - lo) / (hi - lo)) * innenH;
    }

    /* VERDECKTE LINIEN ERKENNEN - VOR der Breitenrechnung.

       `y()` haengt nur an lo/hi und der Hoehe, nicht an der Breite; die
       Erkennung kann deshalb hier stehen und entscheiden, wie viel Platz
       der rechte Rand fuer die Endpunkt-Etiketten braucht. Andersherum
       stuenden die Etiketten ausserhalb des viewBox und waeren unsichtbar -
       ein Etikett, das den Rand nicht bekommt, den es braucht, ist keine
       Loesung fuer eine unsichtbare Linie.

       Am Pixel 10 Pro gemessen: Vodafone 1099,90 EUR, mobilcom-debitel
       1099,00 EUR, Achse von 793 bis 1100 EUR. Neunzig Cent sind auf dieser
       Hoehe weniger als ein Pixel - die Vodafone-Linie stand in der Legende
       und war im Bild nicht da.

       VERSCHOBEN WIRD NICHTS. Die Y-Achse gehoert dem Preis; das ist die
       Lehre aus der geloeschten Positionskarte, deren Etiketten bis zu
       235 px neben ihrem Punkt standen, weil sie einander ausgewichen sind.
       Die verdeckte Linie bekommt eine eigene Strichart und ein Etikett an
       ihrem Ende, beides auf ihrer wahren Hoehe.

       Verglichen wird ueber die GEMEINSAMEN Tage. Zwei Reihen ohne einen
       gemeinsamen Tag koennen einander nicht verdecken - ohne diese
       Bedingung galt ein Anbieter mit einem einzigen Punkt als verdeckt von
       jedem, dessen Kurve zufaellig auf gleicher Hoehe endete. */
    var GRENZE = ABSTAND * innenH;
    var gelegt = [];
    reihen.forEach(function (r) {
      var meine = {};
      r.punkte.forEach(function (p) { meine[p.datum] = y(p.preis); });
      var verdeckt = null;
      for (var i = 0; i < gelegt.length && !verdeckt; i++) {
        var gemeinsam = 0, weit = 0;
        for (var d in meine) {
          if (gelegt[i].ys[d] === undefined) continue;
          gemeinsam++;
          if (Math.abs(meine[d] - gelegt[i].ys[d]) > GRENZE) weit++;
        }
        if (gemeinsam && !weit) verdeckt = gelegt[i].anbieter;
      }
      gelegt.push({ anbieter: r.anbieter, ys: meine });
      r.verdeckt = verdeckt;
    });

    /* K (QA-Fix 24.09.2026): KEINE RESERVIERTE ZEICHENFLAECHE MEHR FUER
       DAS ENDLABEL. Die alte Fassung reservierte pauschal 210 Einheiten
       rechten Rand, sobald ein Etikett noetig war - bei einer festen
       Zeichenflaeche von 1080 Einheiten Breite ein Sechstel, auf dem
       Telefon (jetzt real ~306-390 Einheiten, siehe BREITE oben) blieben
       davon nur rund 20 Einheiten fuer die GANZE Zeitachse: die Kurve
       stand als senkrechter Strich. Das Etikett braucht diese Reserve
       nicht mehr - es haengt jetzt an einem FESTEN X nahe dem rechten
       Bildrand (`ENDLABEL_RAND`, dieselbe Loesung wie der Server-Chart
       `geraete_zeitreihe.py`, dortiger C4-Fix), waechst mit
       `text-anchor='end'` nach LINKS und braucht darum keine Reserve. */
    var innenB = BREITE - RAND.links - RAND.rechts;

    // ZEITPROPORTIONAL, nicht ordinal. Die erste Fassung bildete auf
    // `tageSort.indexOf(datum)` ab: bei Messungen am 10.8., 21.8. und 29.8.
    // (Abstaende 11 und 8 Tage) standen die drei Marken gleich weit
    // auseinander, und die Steigung der Kurve war frei erfunden. Dieselbe
    // Fehlerklasse wie die 235-px-Etiketten der geloeschten Grafik, nur auf
    // der anderen Achse.
    var t0 = tagNr(tageSort[0]);
    var t1 = tagNr(tageSort[tageSort.length - 1]);
    function x(datum) {
      if (t1 === t0) return RAND.links + innenB / 2;
      return RAND.links + ((tagNr(datum) - t0) / (t1 - t0)) * innenB;
    }
    var svg = el('svg', {
      viewBox: '0 0 ' + BREITE + ' ' + HOEHE, class: 'gr-vsvg',
      role: 'img', 'aria-label': 'Preisverlauf ' + g.label
    });

    // Waagerechte Hilfslinien und die Preisachse: vier Stufen reichen, um
    // eine Hoehe abzulesen, und halten die Flaeche ruhig.
    var stufen = flach ? [lo]
                       : [0, 1, 2, 3, 4].map(function (i) {
                           return lo + (hi - lo) * (i / 4);
                         });

    /* KEINE ZWEI ACHSENMARKEN MIT DEMSELBEN TEXT.

       `Math.round` reicht, solange die Spanne mehrere Euro breit ist. Bei
       drei Anbietern zwischen 900,00 und 900,20 EUR stand die Achse
       fuenfmal mit "900 €" da - fuenf Hilfslinien, die behaupten, fuenf
       verschiedene Hoehen zu benennen. Das ist dieselbe Fehlerklasse wie
       die drei "1000 €" bei einem Preis von 999,00: eine Achse, der man
       nicht glauben kann.

       Erst wird auf ganze Euro gerundet; sind zwei Marken dann gleich,
       traegt die ganze Achse zwei Nachkommastellen. Bleiben sie auch dann
       gleich, sind es wirklich dieselben Preise, und die doppelte Linie
       faellt weg. Gerundet wird NUR die Beschriftung - die Linie sitzt auf
       dem gerechneten Wert. */
    /* DEUTSCHE SCHREIBWEISE, MIT TAUSENDERTRENNER - wie ueberall sonst auf
       dieser Seite.

       Der erste Anlauf schrieb "1099 €" ohne Trenner, und die Begruendung
       im Kommentar war, dass `test_die_achse_erfindet_keinen_preis` die
       Marken mit `parseFloat` liest und an "1.099" scheitert. Das ist die
       falsche Richtung: damit war die SEITE an einen schwachen Testparser
       angepasst, und die Achse schrieb 1099, waehrend Tooltip, Legende,
       Kacheln und Tabelle desselben Diagramms 1.099,00 schreiben. Der Test
       liest jetzt richtig; die Achse schreibt, was das Portal schreibt. */
    function achsentext(preis, stellen) {
      return preis.toLocaleString('de-DE', { minimumFractionDigits: stellen,
                                             maximumFractionDigits: stellen })
             + ' €';
    }
    var stellen = 0;
    var grob = stufen.map(function (p) { return achsentext(p, 0); });
    if (grob.length !== grob.filter(function (t, i) {
          return grob.indexOf(t) === i; }).length) {
      stellen = 2;
    }
    var gesetzt = {};
    stufen.forEach(function (preis) {
      var text = achsentext(preis, stellen);
      if (gesetzt[text]) return;
      gesetzt[text] = 1;
      var yy = y(preis);
      svg.appendChild(el('line', { x1: RAND.links, x2: RAND.links + innenB,
                                   y1: yy, y2: yy, class: 'gr-vraster' }));
      svg.appendChild(el('text', { x: RAND.links - 10, y: yy + 4,
                                   class: 'gr-vachse', 'text-anchor': 'end' },
                         text));
    });

    // Datumsachse - waagerecht, hoechstens acht Marken (beschriftung()).
    // Alle Kandidaten werden zunaechst gezeichnet - welche STEHEN BLEIBEN,
    // entscheidet `xMarkenOhneUeberlappung` weiter unten, ERST NACHDEM
    // das SVG im Dokument haengt (siehe deren Kommentar).
    var marken = beschriftung(tageSort);
    var gesehen = {};
    var achsenmarken = [];
    marken.forEach(function (t) {
      var text = markeDE(t, raster);
      // Im Monats- und Quartalsraster koennen zwei Tage dieselbe Marke
      // ergeben. Zweimal "Q3 2026" nebeneinander ist keine Achse.
      if (gesehen[text]) return;
      gesehen[text] = 1;
      var knoten = el('text', { x: x(t), y: HOEHE - RAND.unten + 22,
                                class: 'gr-vachse', 'text-anchor': 'middle' },
                      text);
      svg.appendChild(knoten);
      achsenmarken.push({ knoten: knoten, x: x(t) });
    });

    /* A/E (QA-Fix 24.09.2026): STUFENLINIE STATT SCHRAEGER GERADE, UND
       LUECKEN GEPUNKTET - dieselben zwei Regeln wie der TCO-Server-Chart
       (`geraete_zeitreihe._stufenpfad`/`_linien_laeufe`), hier im Client
       gebaut, weil diese Kurve erst im Browser aus den Rohdaten entsteht
       (Zeitraum-/Raster-Umschalter). Ein Preis gilt vom Messtag an - die
       Linie SPRINGT am naechsten Messtag, sie GLEITET nicht dorthin; eine
       schraege durchgezogene Linie ueber eine Messluecke behauptet eine
       beobachtete Entwicklung, die es in der stillen Zeit nicht gab. */
    function stufenpfad(pkte) {
      var teile = ['M' + pkte[0].x.toFixed(1) + ' ' + pkte[0].y.toFixed(1)];
      for (var i = 1; i < pkte.length; i++) {
        var y0 = pkte[i - 1].y, x1 = pkte[i].x, y1 = pkte[i].y;
        teile.push('L' + x1.toFixed(1) + ' ' + y0.toFixed(1));
        if (y1 !== y0) teile.push('L' + x1.toFixed(1) + ' ' + y1.toFixed(1));
      }
      return teile.join(' ');
    }
    function linienLaeufe(pkte) {
      if (pkte.length < 2) return [];
      var laeufe = [], lauf = [pkte[0]];
      for (var i = 1; i < pkte.length; i++) {
        var tage = tagNr(pkte[i].datum) - tagNr(pkte[i - 1].datum);
        if (tage > LUECKE_TAGE) {
          if (lauf.length > 1) laeufe.push({ pkte: lauf, luecke: false });
          laeufe.push({ pkte: [pkte[i - 1], pkte[i]], luecke: true });
          lauf = [pkte[i]];
        } else {
          lauf.push(pkte[i]);
        }
      }
      if (lauf.length > 1) laeufe.push({ pkte: lauf, luecke: false });
      return laeufe;
    }

    /* M (QA-Fix 24.09.2026): siehe Kommentar an `endlabelListe.push(...)`
       weiter unten - gesammelt hier, gezeichnet NACH der ganzen Schleife. */
    var endlabelListe = [];
    reihen.forEach(function (r) {
      var pkte = r.punkte.map(function (p) {
        return { x: x(p.datum), y: y(p.preis), datum: p.datum };
      });
      if (r.punkte.length > 1) {
        /* P2/D1: die Anbieterklasse (`gr-anb--<slug>`) traegt die
           Strichart aus derselben EINEN Quelle wie die Farbe
           (report/anbieter_farben.py, ueber style.css `--anb-strich`) -
           Farbe allein unterscheidet Vodafone und Telekom nicht sicher
           (ΔE 11,5 unter normalem Sehen, dataviz-Validator). Die Klasse
           bleibt auch im "verdeckt"-Zweig stehen (angehaengt, nicht
           ersetzt), sonst verliert ausgerechnet die ueberdeckte Linie
           ihre Markenkennzeichnung. */
        var klasse = 'gr-vlinie' + (r.slug ? ' gr-anb--' + r.slug : '');
        if (r.verdeckt) {
          /* MEHR LUECKE ALS STRICH. Mit "7 5" deckte die obenliegende Linie
             immer noch 58 Prozent der Laenge ab; am Pixelbild gemessen
             blieben von der verdeckten Linie darunter 197 von 1400 Pixeln
             uebrig, und die eigene (3 px) ueberdeckte die fremde (2 px)
             vollstaendig. Mit "4 8" liegt zwei Dritteln der Strecke die
             untere Linie frei - beide sind zu sehen, und keine ist
             verschoben. Die `--anb-strich`-Regel in style.css gilt
             ausdruecklich nur `:not(.gr-vlinie--verdeckt)` - sie tritt der
             Verdeckungs-Markierung hier nicht in den Weg, das INLINE-
             Attribut bleibt die einzige Quelle des Strichmusters. Diese
             Markierung gilt der GANZEN Linie (verdeckt bleibt verdeckt,
             Luecke hin oder her) - sie ist eine eigene, staerkere Aussage
             als die Messluecke. */
          svg.appendChild(el('path', {
            d: stufenpfad(pkte), fill: 'none', stroke: r.farbe,
            'stroke-width': r.eigen ? 3 : 2, 'stroke-dasharray': '4 8',
            class: klasse + ' gr-vlinie--verdeckt' }));
        } else {
          linienLaeufe(pkte).forEach(function (lauf) {
            var attrs = { d: stufenpfad(lauf.pkte), fill: 'none',
                          stroke: r.farbe, 'stroke-width': r.eigen ? 3 : 2,
                          class: klasse };
            if (lauf.luecke) {
              attrs['stroke-dasharray'] = '2 4';
              attrs.class = klasse + ' gr-vlinie--luecke';
            }
            svg.appendChild(el('path', attrs));
          });
        }
      }
      r.punkte.forEach(function (p) {
        /* Der Punkt der obenliegenden Linie wird ein RING, wenn er auf einem
           fremden Punkt sitzt: gefuellt verdeckte er ihn ganz, und an den
           Messpunkten - genau dort, wo man den Preis abliest - saehe man nur
           einen Anbieter. Der Ring steht auf derselben Hoehe wie der Punkt
           darunter; verschoben wird auch hier nichts. */
        var k = el('circle', {
          cx: x(p.datum), cy: y(p.preis), r: r.eigen ? 5 : 4,
          fill: r.verdeckt ? 'none' : r.farbe,
          stroke: r.verdeckt ? r.farbe : null,
          class: r.verdeckt ? 'gr-vpunkt gr-vpunkt--ring' : 'gr-vpunkt' });
        k.appendChild(el('title', {}, r.anbieter + ': ' + euro(p.preis) +
                                      ' am ' + tagDE(p.datum)));
        svg.appendChild(k);
      });
      /* Das Endpunkt-Etikett bekommt NUR die verdeckte Linie. An jeder Linie
         waere es die Legende ein zweites Mal, und der rechte Rand reicht fuer
         zwei Namen nebeneinander nicht.

         J (QA-Fix 24.09.2026, Entscheidung): am iPhone 17 256 GB traegt
         GENAU EIN Anbieter (mobilcom-debitel, die verdeckte Linie hinter
         Vodafone) ein Endlabel, die anderen fuenf nicht - das ist keine
         Luecke, sondern die Regel oben: das Etikett loest eine ECHTE
         Mehrdeutigkeit (zwei Linien auf derselben Hoehe), es ist keine
         zweite Beschriftung jeder Linie. Ein Etikett je Anbieter braeuchte
         eigene Kollisionsvermeidung UND mehr rechten Rand fuer bis zu
         sechs Namen - gegen Antonios Regel "wenig Text" auf einer Seite,
         die schon eine Legende mit JEDEM Anbieter UND seiner Hausfarbe
         hat (`anbieter_farben.py`, dort auch Telekom-Magenta). Die Legende
         bleibt die eine Stelle, an der jeder Anbieter benannt ist -
         siehe `tests/test_geraete_verlauf_legende_browser.py`. */
      if (r.verdeckt) {
        var letzt = r.punkte[r.punkte.length - 1];
        /* M (QA-Fix 24.09.2026): NICHT HIER EINHAENGEN. Diese Schleife
           haengt Linien und Punkte JE REIHE an, in Reihenfolge - ein
           Endlabel, das HIER angehaengt wird, kann von der PUNKT (oder
           LINIE) der NAECHSTEN Reihe wieder ueberdeckt werden. Die
           Etiketten werden deshalb gesammelt und ERST NACH dieser
           gesamten Schleife gezeichnet (`endlabelListe` unten) - zuletzt
           im SVG, also zuoberst gezeichnet, ueber jeder Linie und jedem
           Punkt. */
        endlabelListe.push({ r: r, letzt: letzt });
      }
    });

    /* M (QA-Fix 24.09.2026): DIE VERDECKT-ENDLABEL - ZULETZT GEZEICHNET
       (siehe Kommentar oben) UND MIT Y-VERSATZ. Am iPhone 17 256 GB lag
       "mobilcom-debitel 1.099,00 €" auf x≈1290 direkt auf der roten
       gestrichelten Vodafone-Linie UND ihren Endpunkten - beide enden
       auf y(letzt.preis), derselben Hoehe wie das unversetzte Etikett.
       ENDLABEL_Y_VERSATZ schiebt es senkrecht weg: nach OBEN, ausser das
       liefe ueber den oberen Rand hinaus (RAND.oben) - dann nach UNTEN.
       Der Halo (`.gr-vetikett`, style.css) haelt den Rest lesbar, falls
       trotzdem eine andere Linie im Weg liegt. */
    endlabelListe.forEach(function (e) {
      var yy = y(e.letzt.preis) - ENDLABEL_Y_VERSATZ;
      if (yy < RAND.oben + 6) yy = y(e.letzt.preis) + ENDLABEL_Y_VERSATZ;
      svg.appendChild(el('text', {
        x: BREITE - ENDLABEL_RAND, y: yy,
        class: 'gr-vetikett', fill: e.r.farbe, 'text-anchor': 'end'
      }, e.r.anbieter + ' ' + euro(e.letzt.preis)));
    });

    /* DER BESTPREIS-STEMPEL (idealo-Muster, 04.09.2026).

       Die Kachel "Niedrigster Preis" sagt, WIE tief es war. Sie sagt nicht,
       WANN - und genau das ist die Frage, die man an einen Verlauf hat.
       Der Stempel beantwortet sie im Bild: ein Ring auf dem tiefsten Punkt
       und darunter das Datum.

       ER TRAEGT DEN PREIS NICHT NOCH EINMAL. Die Zahl steht schon in der
       Kachel, und "eine Zahl steht je Ort genau EINMAL" (Beruhigungsregeln)
       gilt auch dann, wenn die zweite Stelle ein SVG ist. Der Ring sitzt auf
       der Preishoehe, das Etikett auf derselben Hoehe daneben - die Y-Achse
       gehoert dem Preis, hier wird so wenig verschoben wie in der geloeschten
       Positionskarte.

       Bei flacher Reihe entfaellt er: wenn jeder Punkt derselbe Preis ist,
       ist jeder der billigste, und ein Stempel behauptete einen Tiefpunkt,
       den es nicht gibt. */
    var bestMarke = null, bestX = 0;
    if (!flach) {
      var bester = null;
      reihen.forEach(function (r) {
        r.punkte.forEach(function (p) {
          /* Bei gleichem Preis gewinnt der FRUEHERE Tag: gefragt ist, seit
             wann es so billig ist, nicht wer zuletzt nachgezogen hat. */
          if (!bester || p.preis < bester.preis ||
              (p.preis === bester.preis && p.datum < bester.datum)) {
            bester = { preis: p.preis, datum: p.datum,
                       anbieter: r.anbieter, farbe: r.farbe };
          }
        });
      });
      if (bester) {
        var bx = x(bester.datum), by = y(bester.preis);
        var ring = el('circle', {
          cx: bx, cy: by, r: 9, fill: 'none', stroke: bester.farbe,
          class: 'gr-vbest' });
        ring.appendChild(el('title', {}, 'Billigster gemessener Stand: ' +
                            bester.anbieter + ' ' + euro(bester.preis) +
                            ' am ' + tagDE(bester.datum)));
        svg.appendChild(ring);
        /* Das Etikett kippt nach links, sobald es sonst aus dem Bild
           liefe - der tiefste Punkt liegt oft am rechten Rand.

           GEMESSEN, NICHT GESCHAETZT. Die erste Fassung reservierte pauschal
           78 px; im Chromium gemessen ist "billigster Stand 4.8." aber
           110,3 px breit, und bei einem Tiefpunkt auf 92 Prozent der
           Zeitachse standen 30 px ausserhalb der viewBox - abgeschnitten war
           ausgerechnet das Datum, also die einzige Auskunft dieses
           Etiketts. `getComputedTextLength()` gibt es genau dafuer; es
           braucht den Knoten IM Baum, deshalb wird erst angehaengt und dann
           gemessen. */
        bestMarke = el('text', {
          x: bx + 14, y: by + 4, class: 'gr-vbestmarke',
          fill: bester.farbe, 'text-anchor': 'start'
        }, 'billigster Stand ' + tagDE(bester.datum));
        bestX = bx;
        svg.appendChild(bestMarke);
      }
    }
    bild.appendChild(svg);

    /* H2 (QA-Fix 24.09.2026): DATUMSMARKEN OHNE UEBERLAPPUNG - ERST JETZT,
       aus demselben Grund wie `bestMarke` gleich darunter:
       `getComputedTextLength()` braucht den Knoten IM Dokument.

       Dieselbe Regel wie der Server-Chart (`geraete_zeitreihe._x_marken`):
       gierig von links, der ERSTE Tag bleibt immer, jede weitere Marke nur
       ohne Ueberlappung mit der zuletzt behaltenen, die LETZTE ersetzt
       noetigenfalls die vorletzte statt zusaetzlich zu kollidieren - eine
       Achse ohne Enddatum sagt nicht, bis wann sie reicht. Der Server
       misst dort einen FESTEN Mindestabstand (Python kennt keine
       Glyphenbreite); hier steht der echte Browser bereit, gemessen wird
       deshalb die TATSAECHLICHE Breite, nicht geschaetzt - am 24.09.2026
       im Chromium gemessen ueberlappten "11.9." und "12.9." (text-anchor
       middle) um 5 px, eine feste Zeichenbreite haette das je nach
       Schriftfallback verfehlt (Sandbox ohne Google Fonts, siehe
       CLAUDE.md Fallstricke). */
    if (achsenmarken.length > 1) {
      achsenmarken.forEach(function (m) {
        var breite = m.knoten.getComputedTextLength ?
                     m.knoten.getComputedTextLength() : 0;
        m.links = m.x - breite / 2; m.rechts = m.x + breite / 2;
      });
      var behaltenMarken = [achsenmarken[0]];
      for (var mi = 1; mi < achsenmarken.length - 1; mi++) {
        var kandidat = achsenmarken[mi];
        var letzteMarke = behaltenMarken[behaltenMarken.length - 1];
        if (kandidat.links - letzteMarke.rechts >= X_MARKEN_LUECKE) {
          behaltenMarken.push(kandidat);
        } else {
          svg.removeChild(kandidat.knoten);
        }
      }
      var letzteAchsenmarke = achsenmarken[achsenmarken.length - 1];
      var vorletzteMarke = behaltenMarken[behaltenMarken.length - 1];
      if (behaltenMarken.length > 1 && letzteAchsenmarke.links -
          vorletzteMarke.rechts < X_MARKEN_LUECKE) {
        svg.removeChild(vorletzteMarke.knoten);
        behaltenMarken[behaltenMarken.length - 1] = letzteAchsenmarke;
      } else if (letzteAchsenmarke !== vorletzteMarke) {
        behaltenMarken.push(letzteAchsenmarke);
      }
    }

    /* ERST JETZT MESSEN. `getComputedTextLength()` gibt an einem Knoten
       ausserhalb des Dokuments 0 zurueck - der Zweig kippte dann nie, und
       der Test fand das Etikett 112 px ausserhalb der viewBox. Der Baum
       oben wird detached aufgebaut; die Messung gehoert deshalb hinter das
       Einhaengen und nicht davor. */
    if (bestMarke) {
      var breit = bestMarke.getComputedTextLength ?
                  bestMarke.getComputedTextLength() : 0;
      var bmX = bestX + 14, bmAnchorEnd = false;
      if (bmX + breit > BREITE - 6) {
        bmX = bestX - 14;
        bmAnchorEnd = true;
      }
      /* K (QA-Fix 24.09.2026): DIE ZWEITE KANTE - links. Der Kipp-Zweig
         oben hilft gegen den RECHTEN Bildrand; auf einer schmalen
         Zeichenflaeche (Telefon, `BREITE` jetzt die echte Containerbreite,
         siehe oben) kann dieselbe Etikettbreite (110 px bei "billigster
         Stand 3.9.", unveraendert seit die Schrift echte 12 px hat) nach
         dem Kippen selbst ueber den LINKEN Rand hinaus in die Y-Achsen-
         Beschriftung laufen - beide enden gemessen an der Achse, das
         Etikett darueber. Die linke Kante bleibt deshalb nie vor
         `RAND.links`, unabhaengig von der Ankerrichtung; noetigenfalls
         ueberlappt das Etikett dann eher die Kurve als die Achse - die
         Kurve traegt seit diesem Fix ohnehin einen Halo (`.gr-vbestmarke`
         `paint-order:stroke`), die Achsenzahl nicht. */
      var linkeKante = bmAnchorEnd ? bmX - breit : bmX;
      if (linkeKante < RAND.links) {
        bmX = bmAnchorEnd ? RAND.links + breit : RAND.links;
      }
      bestMarke.setAttribute('x', bmX);
      if (bmAnchorEnd) bestMarke.setAttribute('text-anchor', 'end');
    }

    reihen.forEach(function (r) {
      var s = document.createElement('span');
      s.className = 'gr-vlegende-teil';
      var punkt = document.createElement('span');
      punkt.className = 'gr-vlegende-punkt';
      punkt.style.background = r.farbe;
      s.appendChild(punkt);
      s.appendChild(document.createTextNode(r.anbieter));
      legende.appendChild(s);
    });

    tabelleBauen(reihen);
  }

  /* Die Tabelle unter dem Diagramm - und OHNE Diagramm die ganze Antwort.

     Sie steht als eigene Funktion, seit das Gatter darueber sie auch dann
     braucht, wenn kein Bild gezeichnet wird. Zwei Kopien dieser Rechnung
     waeren zwei Meinungen darueber, was "aktueller Preis" heisst. */
  function tabelleBauen(reihen) {
    var t = document.createElement('table');
    t.className = 'src-table gr-tabelle';
    var tb = document.createElement('tbody');
    // AUS DEN GEFILTERTEN REIHEN, nicht aus der vorgerechneten Liste.
    // `g.aktuell` rechnet ueber den vollen Zeitraum; mit einem Von-Datum vom
    // 29.08. nannte die Tabelle einen Anbieter, der im Diagramm daneben gar
    // nicht vorkam, mit einem Datum ausserhalb des gewaehlten Fensters.
    // Zwei Zahlen fuer dieselbe Sache auf einem Bildschirm.
    var zeilen = reihen.map(function (r) {
      var ps = r.punkte;
      var letzt = ps[ps.length - 1];
      var aend = null;
      if (ps.length > 1 && ps[0].preis !== letzt.preis) {
        aend = Math.round((letzt.preis - ps[0].preis) * 100) / 100;
      }
      return { anbieter: r.anbieter, eigen: r.eigen, preis: letzt.preis,
               stand: letzt.datum, veraenderung: aend };
    }).sort(function (a, b) { return a.preis - b.preis; });

    /* EINE SPALTE AUS LAUTER STRICHEN IST KEINE SPALTE.

       "Veraenderung" bleibt leer, solange ein Anbieter nur einen Messpunkt
       hat oder sein Preis sich nicht bewegt hat - beides ist richtig so
       ("-0,00 EUR" waere keine Auskunft). Am Galaxy S25 standen damit drei
       Zeilen mit drei Gedankenstrichen untereinander, und eine Spalte, in
       der nichts steht, liest sich als kaputte Seite und nicht als ruhiger
       Markt. Sie erscheint deshalb nur, wenn wenigstens EIN Wert darin
       steht - dieselbe Regel, mit der "niemand guenstiger" aus der
       Alarmtabelle geflogen ist. */
    var mitAenderung = zeilen.some(function (z) {
      return z.veraenderung !== null;
    });
    t.innerHTML = '<thead><tr><th scope="col">Anbieter</th>' +
      '<th scope="col" class="num">aktueller Preis</th>' +
      (mitAenderung ? '<th scope="col" class="num">Veränderung</th>' : '') +
      '<th scope="col">zuletzt aktualisiert</th></tr></thead>';

    zeilen.forEach(function (z) {
      var tr = document.createElement('tr');
      var d = z.veraenderung === null ? '–'
            : (z.veraenderung > 0 ? '+' : '') + euro(z.veraenderung);
      // `textContent` statt `innerHTML`: der Anbietername ist ein DATENWERT.
      // `_quellenlage` kennt ausdruecklich Anbieter, die nur in der
      // Datenbank stehen und nicht in der Konfiguration - Legende und
      // Trefferliste setzen ihn laengst als Text.
      var werte = mitAenderung
        ? [z.anbieter, euro(z.preis), d, markeDE(z.stand, raster)]
        : [z.anbieter, euro(z.preis), markeDE(z.stand, raster)];
      werte.forEach(function (wert, i) {
        var td = tr.insertCell(-1);
        if (i === 1 || (mitAenderung && i === 2)) td.className = 'num';
        td.textContent = wert;
      });
      if (z.eigen) tr.className = 'gr-veigen';
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    tabelle.appendChild(t);
  }

  function waehle(g, vomLeser) {
    gewaehlt = g;
    feld.value = g.label;
    if (vomLeser) {
      TR_LESER_MODELL = g.id;
      try {
        var p = new URLSearchParams(location.search);
        p.set('modell', g.id);
        history.replaceState(null, '', '?' + p.toString() + location.hash);
      } catch (e) { /* Datei-Offline: kein replaceState noetig */ }
    }
    treffer.hidden = true;
    feld.setAttribute('aria-expanded', 'false');
    steuer.hidden = false;
    zeichne(g);
  }

  feld.addEventListener('input', function () {
    var q = feld.value.trim().toLowerCase();
    treffer.innerHTML = '';
    // Sobald der Leser weitertippt, gilt die alte Auswahl nicht mehr. Ohne
    // diesen Rueckbau stand unter dem Suchwort "zzzz" unveraendert der
    // Verlauf des zuletzt gewaehlten Geraets.
    if (gewaehlt && feld.value !== gewaehlt.label) {
      gewaehlt = null;
      steuer.hidden = true; kacheln.hidden = true;
      bild.hidden = true; legende.hidden = true; tabelle.hidden = true;
      bild.innerHTML = ''; legende.innerHTML = ''; tabelle.innerHTML = '';
      leer.hidden = false;
      // P2-Fix (Sicht-Prüfung 17.09.): „Kein Gerät gefunden." statt des
      // sieben-Wort-Bedinungshinweises - kein Satz auf dieser Seite erklärt
      // ihre Bedienung. Der Text steht ZWEIMAL im Code (hier und in der
      // Vorlage) und ein Test hält beide zusammen.
      leer.textContent = 'Kein Gerät gefunden.';
      // AUCH DIE ZWEI SAETZE. Ohne das stand unter dem Rückbau-Satz weiter
      // "Für dieses Gerät liegen 2 Messtermine vor, vom 3.8. bis zum 4.8."
      // - ein Satz ueber ein Geraet, das nicht mehr gewaehlt ist -, und die
      // globale Zahl war von der Seite verschwunden, weil `satzFuer` sie
      // beim Gattern ausgeblendet hatte.
      if (zukurz) { zukurz.hidden = true; zukurz.textContent = ''; }
      satzFuer(null, null, 0);
    }
    if (q.length < 2) {
      treffer.hidden = true;
      feld.setAttribute('aria-expanded', 'false');
      return;
    }
    var gefunden = GERAETE.filter(function (g) {
      return g.suchtext.indexOf(q) !== -1;
    }).slice(0, 8);
    gefunden.forEach(function (g) {
      var li = document.createElement('li');
      li.className = 'gr-vtreffer-zeile';
      li.setAttribute('role', 'option');
      li.tabIndex = 0;
      // P2-Fix (Sicht-Prüfung 17.09.): der Ternär hier hatte zwei
      // IDENTISCHE Zweige (' Anbieter' : ' Anbieter') - toter Code.
      li.textContent = g.label + ' · ' + g.anbieter + ' Anbieter';
      li.addEventListener('click', function () { waehle(g, true); });
      li.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); waehle(g, true); }
      });
      treffer.appendChild(li);
    });
    treffer.hidden = !gefunden.length;
    feld.setAttribute('aria-expanded', gefunden.length ? 'true' : 'false');
  });

  Array.prototype.forEach.call(
    document.querySelectorAll('.gr-vknopf'), function (k) {
      k.addEventListener('click', function () {
        Array.prototype.forEach.call(document.querySelectorAll('.gr-vknopf'),
          function (a) { a.classList.remove('is-aktiv'); });
        k.classList.add('is-aktiv');
        raster = k.getAttribute('data-raster');
        if (gewaehlt) zeichne(gewaehlt);
      });
    });
  [von, bis].forEach(function (d) {
    if (d) d.addEventListener('change', function () {
      if (gewaehlt) zeichne(gewaehlt);
    });
  });

  /* AUTO-VORAUSWAHL (P2, Antonio F4, 17.09.2026). Bis P2 startete der
     Reiter mit einem Satz statt einem Bild - die B4-Regel „ohne Auswahl
     kein Diagramm". Sie schuetzte den Zustand, in dem ueber dem Wähler
     noch der feste G2-Marktgraph stand; seit sein Fall (P2) waere der
     Reiter sonst grafiklos aufgegangen. Ohne jeden Klick ist jetzt das
     ERSTE Geraet der Liste gewaehlt - die Liste kommt nach Messtagen
     sortiert aus `geraete_verlauf` (`-messpunkte`), das meistgemessene
     steht also oben. Ein ?modell=-Deep-Link hat Vorrang, wenn dessen
     Modell in dieser Liste liegt (der Schluesselraum ist derselbe wie
     der der Zeitreihe); gelesen wird TR_ANKUNFT_SEARCH, nicht die
     aktuelle Adresse - die Zeitreihe des Vergleichs-Reiters schreibt
     beim Laden ihr eigenes ?modell= per replaceState hinein, und das
     waere interne Zustandsspeicherung, kein Leser-Wunsch. Eine
     unbekannte id faellt still auf das erste Geraet zurueck - derselbe
     Grundsatz wie beim Deep-Link des Vergleichs-Reiters. */
  var startGeraet = null;
  try {
    var wunschId = new URLSearchParams(TR_ANKUNFT_SEARCH).get('modell');
    if (wunschId) {
      for (var i = 0; i < GERAETE.length; i++) {
        if (GERAETE[i].id === wunschId) { startGeraet = GERAETE[i]; break; }
      }
    }
  } catch (e) { /* aeltere Browser: erstes Geraet */ }
  waehle(startGeraet || GERAETE[0]);

  /* K (QA-Fix 24.09.2026): NEU ZEICHNEN, WENN DER REITER SICHTBAR WIRD.
     Die Auto-Vorauswahl zwei Zeilen oben zeichnet oft VOR dem ersten Klick
     auf "Preisverlauf" - der Reiter ist zu dem Zeitpunkt noch
     `.gr-tafel--aus` (`display:none`), und die Breitenmessung in
     `zeichne()` faellt auf die Basisbreite zurueck; dieselbe Ursache, aus
     der `getComputedTextLength()` an einem unsichtbaren Knoten 0
     zurueckgibt (Kommentar an der X-Achsen-Ausduennung oben) - beide
     Effekte trafen bis zu diesem Fix denselben ersten, verdeckten
     Zeichenvorgang. Der Tab-Umschalter weiter oben in dieser Datei feuert
     `gr-tafel-sichtbar` auf der Tafel, sobald sie aktiv wird - hier reicht
     das, um mit der jetzt echten Containerbreite neu zu zeichnen. */
  /* EIN GERAET FUER BEIDE REITER (28.09.2026): wird dieser Reiter
     sichtbar, zeigt er das Geraet des Lesers (`TR_LESER_MODELL`, oben in
     der Datei), sofern es dafuer Barpreise gibt - sonst bleibt seine
     Auswahl. */
  function leserGeraet() {
    var id = TR_LESER_MODELL;
    /* Tippt der Leser gerade (keine Auswahl), bleibt sein Suchwort. */
    if (!id || !gewaehlt || gewaehlt.id === id) return null;
    for (var j = 0; j < GERAETE.length; j++) {
      if (GERAETE[j].id === id) return GERAETE[j];
    }
    return null;
  }
  var tafel = document.getElementById('tafel-verlauf');
  if (tafel) {
    tafel.addEventListener('gr-tafel-sichtbar', function () {
      var neu = leserGeraet();
      if (neu) waehle(neu);
      else if (gewaehlt) zeichne(gewaehlt);
    });
  }

  /* RESIZE, ENTPRELLT: dieselbe gemessene Breite aendert sich mit dem
     Fenster (Drehen, Splitscreen, DevTools). Nur zeichnen, wenn die Tafel
     gerade sichtbar ist UND ein Geraet gewaehlt wurde - sonst gibt es
     nichts neu zu messen. */
  var resizeZeitgeber = null;
  window.addEventListener('resize', function () {
    if (resizeZeitgeber) clearTimeout(resizeZeitgeber);
    resizeZeitgeber = setTimeout(function () {
      if (gewaehlt && tafel && !tafel.classList.contains('gr-tafel--aus')) {
        zeichne(gewaehlt);
      }
    }, 150);
  });

  /* Sprung aus der Liste "Über 10 % teurer" (Einzelgerät) in den
     Preisverlauf: Schalter auf Einzelgerät, Gerät wählen, hinscrollen. */
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest ? ev.target.closest('a.gx-vsprung') : null;
    if (!a) return;
    var id = a.getAttribute('data-geraet'), g = null;
    for (var k = 0; k < GERAETE.length; k++) {
      if (GERAETE[k].id === id) { g = GERAETE[k]; break; }
    }
    if (!g) return;
    ev.preventDefault();
    var knopf = document.querySelector(
      '.gr-reiter button[data-tafel="tafel-verlauf"]');
    if (knopf && knopf.getAttribute('aria-selected') !== 'true') knopf.click();
    waehle(g, true);
    var ziel = document.getElementById('verlauf');
    if (ziel) ziel.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
})();

/* LIQUID GLASS (Antonio, 11.10.2026): die Pille liegt unter der Wahl und
   gleitet mit, wenn sie wechselt. Ueber Bildern und waehrend der Inhalt
   rollt wird das Glas klarer. Die Brechung (Karte vom Server, Rechenweg
   github.com/shuding/liquid-glass, MIT, (c) 2025 Shu Ding) bekommt nur
   Chromium; der Filter folgt der echten Groesse des Umschalters. */
(function () {
  var schalter = document.querySelectorAll('[data-glas]');
  if (!schalter.length) return;
  var marken = (navigator.userAgentData && navigator.userAgentData.brands) || [];
  for (var m = 0; m < marken.length; m++) {
    if (marken[m].brand === 'Chromium') document.documentElement.classList.add('glas-chromium');
  }
  /* Ueber einem Bild heisst: das oberste, was unter der Mitte des Glases
     zu sehen ist, ist ein Bild - nicht ein Abschnitt, der ein Bild nur
     enthaelt. Eine deckende Flaeche davor beendet die Suche. */
  var ruhig = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var filter = document.getElementById('glas-linse');
  var bildartig = 'img,video,picture,canvas';

  Array.prototype.forEach.call(schalter, function (s) {
    var pille = s.querySelector('.glas-pille');
    var lege = function (gleiten) {
      var an = s.querySelector('[aria-current="page"],[aria-selected="true"]');
      if (!pille || !an) return;
      s.style.setProperty('--x', an.offsetLeft + 'px');
      s.style.setProperty('--w', an.offsetWidth + 'px');
      if (gleiten && !ruhig) {
        s.classList.remove('gleitet');
        void s.offsetWidth;
        s.classList.add('gleitet');
      }
      if (filter) {
        var r = s.getBoundingClientRect();
        var w = Math.round(r.width), h = Math.round(r.height);
        filter.setAttribute('width', w);
        filter.setAttribute('height', h);
        var bild = filter.querySelector('feImage');
        if (bild) { bild.setAttribute('width', w); bild.setAttribute('height', h); }
      }
    };
    lege(false);
    requestAnimationFrame(function () { s.classList.add('bereit'); });
    new MutationObserver(function () { lege(true); }).observe(s, {
      attributes: true, subtree: true, attributeFilter: ['aria-selected', 'aria-current']
    });
    window.addEventListener('resize', function () { lege(false); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { lege(false); });

    var links = s.querySelectorAll('a[href]');
    for (var i = 0; i < links.length; i++) {
      links[i].addEventListener('click', function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || this.getAttribute('aria-current')) return;
        var alt = s.querySelector('[aria-current]');
        if (alt) alt.removeAttribute('aria-current');
        this.setAttribute('aria-current', 'page');
      });
    }

    var untersuche = function () {
      var r = s.getBoundingClientRect();
      var unter = document.elementsFromPoint ? document.elementsFromPoint(r.left + r.width / 2, r.top + r.height / 2) : [];
      var bild = false;
      for (var j = 0; j < unter.length; j++) {
        var el = unter[j];
        if (s.contains(el)) continue;
        if (el.matches && el.matches(bildartig)) { bild = true; break; }
        var st = getComputedStyle(el);
        if (st.backgroundImage.indexOf('url(') >= 0) { bild = true; break; }
        var farbe = /rgba?\(([^)]+)\)/.exec(st.backgroundColor);
        var deckung = farbe ? farbe[1].split(',') : [];
        if (deckung.length === 3 || (deckung.length === 4 && parseFloat(deckung[3]) > 0.5)) break;
      }
      s.setAttribute('data-unter', bild ? 'bild' : 'flaeche');
    };
    var bedienbar = 'button,a[href],input,select,textarea,label,summary,[role="tab"],[role="button"]';
    var kopf = document.getElementById('kopf');
    var weiche = function () {
      if (getComputedStyle(s).position !== 'sticky') { s.classList.remove('weicht'); return; }
      var r = s.getBoundingClientRect();
      var faellig = false;
      for (var k = 0; k < 15 && !faellig; k++) {
        var unter = document.elementsFromPoint ? document.elementsFromPoint(r.left + r.width * (k % 5 + 0.5) / 5, r.top + r.height * (Math.floor(k / 5) + 1) / 4) : [];
        for (var m = 0; m < unter.length; m++) {
          var el = unter[m];
          if (s.contains(el) || (kopf && kopf.contains(el))) continue;
          if (el.closest && el.closest(bedienbar)) { faellig = true; break; }
        }
      }
      s.classList.toggle('weicht', faellig);
    };
    var still = null, angefragt = false;
    window.addEventListener('scroll', function () {
      s.classList.add('rollt');
      clearTimeout(still);
      still = setTimeout(function () { s.classList.remove('rollt'); }, 180);
      if (angefragt) return;
      angefragt = true;
      requestAnimationFrame(function () { angefragt = false; untersuche(); weiche(); });
    }, { passive: true });
    untersuche();
    weiche();
  });
})();

/* KI-SEITE, SCHNITTE 8 UND 9 (Pitch 9, Entwurf 10). Die Rubrikleiste
   erscheint, sobald der Kopf vorbei ist; hervorgehoben ist der innerste
   Teil, der die Lesezeile kreuzt (das Fenster der Modelle liegt in den
   Meldungen, Antonio 14.10.2026). */
(function () {
  var still = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  [].forEach.call(document.querySelectorAll('.ki-ansage'), function (ansage) {
    if (!('IntersectionObserver' in window)) return ansage.classList.add('da');
    new IntersectionObserver(function (e, o) {
      if (e[0].isIntersecting) { ansage.classList.add('da'); o.disconnect(); }
    }, { threshold: 0.4 }).observe(ansage);
  });

  /* Schnitt 9: die Linie der Fahrt zeichnet sich mit dem Scrollen, der
     rote Punkt laeuft mit, jede erreichte Station poppt auf. Ohne JS steht
     alles fertig im HTML. Unter 700 px groessere Schrift, hoehere viewBox. */
  var weg = document.querySelector('#verstehen .ki-fahrt-weg');
  if (weg) {
    var bild = weg.ownerSVGElement, L = weg.getTotalLength();
    var zuege = [].map.call(bild.querySelectorAll('.ki-zug'), function (g) {
      return { g: g, an: +g.getAttribute('data-an'), anker: g.getAttribute('data-anker') };
    });
    var fpunkt = bild.querySelector('.ki-fahrt-punkt');
    var lege = function () {
      var FS = bild.parentNode.clientWidth < 700 ? 46 : 24;
      bild.setAttribute('viewBox', FS > 30 ? '0 -60 1000 340' : '0 0 1000 260');
      zuege.forEach(function (z) {
        var p = weg.getPointAtLength(L * z.an), t = z.g.querySelector('text'), r = z.g.querySelector('rect'), k = z.g.querySelector('circle');
        t.setAttribute('font-size', FS);
        t.setAttribute('x', p.x);
        t.setAttribute('y', p.y - FS * 1.25);
        var tw = t.getComputedTextLength() + FS * 1.2;
        var x = z.anker === 'start' ? p.x - FS * 0.6 : z.anker === 'end' ? p.x - tw + FS * 0.6 : p.x - tw / 2;
        [['x', x], ['y', p.y - FS * 2.5], ['width', tw], ['height', FS * 1.8], ['rx', FS * 0.9]].forEach(function (a) { r.setAttribute(a[0], a[1]); });
        k.setAttribute('cx', p.x);
        k.setAttribute('cy', p.y);
      });
    };
    var setze = function (u) {
      weg.style.strokeDashoffset = L * (1 - u);
      var p = weg.getPointAtLength(L * u);
      fpunkt.setAttribute('cx', p.x);
      fpunkt.setAttribute('cy', p.y);
      zuege.forEach(function (z) { z.g.classList.toggle('weg', u < z.an - 0.01); });
    };
    var fakt = still ? 1 : 0, fziel = fakt, flaeuft = false;
    var fschritt = function () {
      var d = fziel - fakt;
      fakt += d * 0.12;
      if (Math.abs(d) < 0.001) fakt = fziel;
      setze(fakt);
      if (fakt !== fziel) requestAnimationFrame(fschritt); else flaeuft = false;
    };
    var frechne = function () {
      var r = bild.getBoundingClientRect();
      fziel = still ? 1 : Math.max(0, Math.min(1, (innerHeight * 0.9 - r.top) / (innerHeight * 0.55)));
      if (!flaeuft) { flaeuft = true; requestAnimationFrame(fschritt); }
    };
    weg.style.strokeDasharray = L;
    lege();
    setze(fakt);
    addEventListener('scroll', frechne, { passive: true });
    addEventListener('resize', lege);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(lege);
    frechne();
  }

  var rub = document.getElementById('ki-rubriken'), kopf = document.querySelector('.ki-auftakt');
  if (!rub || !kopf) return;
  var links = rub.querySelectorAll('a');
  var ziele = [].map.call(links, function (a) { return document.querySelector(a.getAttribute('href')); });
  var geplant = false;
  function lage() {
    geplant = false;
    rub.classList.toggle('da', kopf.getBoundingClientRect().bottom < 0);
    var i = -1;
    var zeile = innerHeight * 0.45, tiefe = -1;
    ziele.forEach(function (z, j) {
      if (!z) return;
      var r = z.getBoundingClientRect(), t = 0;
      for (var e = z; e; e = e.parentElement) t++;
      if (r.top < zeile && r.bottom > zeile && t > tiefe) { i = j; tiefe = t; }
    });
    [].forEach.call(links, function (a, j) { a.classList.toggle('an', i === j); });
  }
  addEventListener('scroll', function () {
    if (!geplant) { geplant = true; requestAnimationFrame(lage); }
  }, { passive: true });
  lage();
})();

/* KI-SEITE, SCHNITT 13 (Pitch 9, Entwurf 10). Muster-Prompts: ein Thema auf
   einmal. Die Daten liest das Skript aus den <details> des HTML (ohne JS
   stehen alle Themen untereinander); links die Titel des Themas, rechts das
   Panel mit „Kopieren“, unter 860 px steht das Panel unter dem Titel. */
(function () {
  var abschnitt = document.getElementById('prompts');
  var raster = abschnitt && abschnitt.querySelector('.ki-p-raster');
  if (!raster) return;
  var reiter = abschnitt.querySelectorAll('.ki-p-themen a');
  var P = [].map.call(raster.querySelectorAll('.ki-p-gruppe'), function (g) {
    return [].map.call(g.querySelectorAll('details'), function (d) {
      return [d.querySelector('summary').textContent, d.querySelector('pre').textContent];
    });
  });
  raster.innerHTML = '';
  raster.classList.add('ki-p-raster--an');
  var liste = document.createElement('div');
  liste.className = 'ki-p-liste';
  var panel = document.createElement('div');
  panel.className = 'ki-p-panel';
  panel.innerHTML = '<div class="ki-p-kopf"><b class="ki-p-name"></b>' +
    '<button type="button" class="ki-p-kopieren">Kopieren</button></div><pre class="ki-p-text"></pre>';
  raster.appendChild(liste);
  raster.appendChild(panel);
  var schmal = window.matchMedia('(max-width:860px)'), akt = null, aktKnopf = null;
  function lege() { if (schmal.matches && aktKnopf) aktKnopf.after(panel); else raster.appendChild(panel); }
  function zeige(b, p) {
    akt = p; aktKnopf = b;
    panel.querySelector('.ki-p-name').textContent = p[0];
    panel.querySelector('.ki-p-text').textContent = p[1];
    [].forEach.call(liste.querySelectorAll('.ki-p-titel'), function (e) { e.classList.toggle('an', e === b); });
    lege();
  }
  function thema(gi) {
    [].forEach.call(reiter, function (t, i) {
      t.classList.toggle('an', i === gi);
      if (i === gi) t.setAttribute('aria-current', 'true'); else t.removeAttribute('aria-current');
    });
    raster.appendChild(panel);
    liste.innerHTML = '';
    var erst = null;
    P[gi].forEach(function (p) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'ki-p-titel'; b.textContent = p[0];
      b.addEventListener('click', function () { zeige(b, p); });
      liste.appendChild(b);
      if (!erst) erst = [b, p];
    });
    zeige(erst[0], erst[1]);
  }
  [].forEach.call(reiter, function (a, i) {
    a.addEventListener('click', function (e) { e.preventDefault(); thema(i); });
  });
  if (schmal.addEventListener) schmal.addEventListener('change', lege);
  thema(0);
  var k = panel.querySelector('.ki-p-kopieren');
  function ok() {
    k.textContent = 'Kopiert'; k.classList.add('ok');
    setTimeout(function () { k.textContent = 'Kopieren'; k.classList.remove('ok'); }, 1600);
  }
  function ersatz() {
    var f = document.createElement('textarea');
    f.value = akt[1]; f.setAttribute('readonly', ''); f.style.position = 'fixed'; f.style.opacity = '0';
    document.body.appendChild(f); f.select();
    var gut = false;
    try { gut = document.execCommand('copy'); } catch (e) { gut = false; }
    f.remove();
    if (gut) ok();
  }
  k.addEventListener('click', function () {
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(akt[1]).then(ok, ersatz);
    else ersatz();
  });
})();

/* KI-SEITE, SCHNITTE 14 UND 15 (Pitch 9, Entwurf 10). Videos: das HTML
   traegt nur das eigene Standbild und den Link zu YouTube. Erst ein Klick
   ersetzt das Standbild durch das iframe von youtube-nocookie, vorher geht
   beim Aufruf nichts an Google. */
(function () {
  [].forEach.call(document.querySelectorAll('.ki-player[data-ki-video]'), function (b) {
    b.addEventListener('click', function () {
      var f = document.createElement('iframe');
      f.className = 'ki-player';
      f.src = 'https://www.youtube-nocookie.com/embed/' +
        encodeURIComponent(b.getAttribute('data-ki-video')) + '?autoplay=1&rel=0';
      f.title = b.getAttribute('aria-label');
      f.setAttribute('allow', 'autoplay; encrypted-media; picture-in-picture');
      f.setAttribute('allowfullscreen', '');
      var video = b.closest('.ki-video');
      if (video) video.classList.add('ki-video--offen');
      b.replaceWith(f);
    });
  });
})();

/* KI-SEITE, SCHNITTE 10 BIS 12 (Pitch 9, Entwurf 10). Kapitel 1: die
   Fahrt durch die Linienzeichnung. Alle Koordinaten stehen fertig im HTML
   (ki_kapitel_bild.py); hier wird nur bewegt. Der rote Punkt folgt der
   Route bis zur Hoehe der Bildschirmmitte, Linien zeichnen sich, sobald sie
   ins Bild kommen, Pillen poppen auf (data-y), Zaehler laufen hoch und
   Markierungen schalten, wenn der Punkt sie erreicht (data-an). Ohne JS
   und bei reduzierter Bewegung steht alles fertig da; der Punkt springt
   dann ohne Nachlauf. */
(function () {
  var welt = document.getElementById('ki-k1-welt');
  if (!welt) return;
  var still = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var reise = welt.parentNode;
  var W = welt.viewBox.baseVal.width;
  var route = welt.querySelector('.ki-k1-route');
  var punkt = welt.querySelector('.ki-k1-punkt'), halo = welt.querySelector('.ki-k1-halo');
  var L = route.getTotalLength();
  function alle(sel) { return [].slice.call(reise.querySelectorAll(sel)); }
  function cl(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function ez(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  var tabelle = [], maxY = -1;
  for (var s = 0; s <= L; s += 3) {
    maxY = Math.max(maxY, route.getPointAtLength(s).y);
    tabelle.push([s, maxY]);
  }
  function laengeBis(y) {
    var lo = 0, hi = tabelle.length - 1;
    if (y <= tabelle[0][1]) return 0;
    while (lo < hi) { var m = (lo + hi + 1) >> 1; if (tabelle[m][1] <= y) lo = m; else hi = m - 1; }
    return tabelle[lo][0];
  }
  var ziehen = alle('.ki-k1-zieh, .ki-k1-sehne').map(function (p) {
    var len = p.getTotalLength();
    if (!still) { p.style.strokeDasharray = len; p.style.strokeDashoffset = len; }
    return { p: p, len: len, y: +p.getAttribute('data-y'), h: +p.getAttribute('data-h'), sehne: p.classList.contains('ki-k1-sehne') };
  });
  var zuege = alle('.ki-k1-zug[data-y]').map(function (g) { return { g: g, y: +g.getAttribute('data-y') }; });
  var saetze = alle('.ki-k1-satz').map(function (e) { return { e: e, y: +e.getAttribute('data-y') }; });
  var marken = alle('[data-an]').map(function (e) { return { e: e, y: +e.getAttribute('data-an') }; });
  var zaehler = alle('.ki-k1-zahl').map(function (e) { return { e: e, y: +e.getAttribute('data-y'), ziel: +e.textContent, fertig: still }; });
  var raeder = alle('.ki-k1-rad').map(function (g) {
    return { g: g, cx: g.getAttribute('data-cx'), cy: g.getAttribute('data-cy'), f: +g.getAttribute('data-f') };
  });
  var ringe = alle('.ki-k1-ring').map(function (g) { return { g: g, f: +g.getAttribute('data-f') }; });
  if (!still) {
    route.style.strokeDasharray = L;
    zaehler.forEach(function (z) { z.e.textContent = '00000'; });
  }
  var akt = 0, ziel = 0, laeuft = false;
  function zaehle(z) {
    z.fertig = true;
    var t0 = performance.now();
    (function lauf(t) {
      var k = cl((t - t0) / 900);
      z.e.textContent = String(Math.round(z.ziel * ez(k))).padStart(5, '0');
      if (k < 1) requestAnimationFrame(lauf);
    })(t0);
  }
  function schritt() {
    var d = ziel - akt;
    akt += still ? d : d * 0.12;
    if (Math.abs(d) < 0.4) akt = ziel;
    var p = route.getPointAtLength(akt);
    [punkt, halo].forEach(function (k) { k.setAttribute('cx', p.x); k.setAttribute('cy', p.y); });
    if (!still) route.style.strokeDashoffset = L - akt;
    zaehler.forEach(function (z) { if (!z.fertig && p.y >= z.y - 30) zaehle(z); });
    marken.forEach(function (m) {
      if (m.e.classList.contains('da') || p.y < m.y) return;
      m.e.classList.add('da');
      if (!still && m.e.classList.contains('ki-k1-sehne')) m.e.style.strokeDashoffset = 0;
    });
    if (akt !== ziel) requestAnimationFrame(schritt); else laeuft = false;
  }
  function bild() {
    var r = welt.getBoundingClientRect(), skala = r.width / W;
    var unten = (innerHeight - r.top) / skala, mitte = (innerHeight * 0.5 - r.top) / skala;
    if (!still) {
      ziehen.forEach(function (z) {
        if (!z.sehne) z.p.style.strokeDashoffset = z.len * (1 - ez(cl((unten - z.y - 40) / (z.h * 0.8 + 260))));
      });
      zuege.forEach(function (z) { z.g.classList.toggle('weg', z.y > unten - 60); });
      saetze.forEach(function (z) { z.e.classList.toggle('da', z.y < unten - 80); });
      raeder.forEach(function (z) { z.g.setAttribute('transform', 'rotate(' + (scrollY * 0.25 * z.f) + ' ' + z.cx + ' ' + z.cy + ')'); });
      ringe.forEach(function (z) { z.g.setAttribute('transform', 'translate(0,' + (-(scrollY / skala) * z.f) + ')'); });
    }
    ziel = laengeBis(mitte);
    if (!laeuft) { laeuft = true; requestAnimationFrame(schritt); }
  }
  if (still) marken.forEach(function (m) { m.e.classList.add('da'); });
  addEventListener('scroll', bild, { passive: true });
  addEventListener('resize', bild);
  bild();
})();
