/* Service worker mínimo de AuraVox: solo para mostrar las notificaciones de
   los recordatorios (en Android, Chrome no deja crearlas de otra forma) y
   para que tocar una abra la página. No guarda nada en caché. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (all.length) return all[0].focus();
    return self.clients.openWindow("/");
  })());
});
