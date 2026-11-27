/* ==========================================================
   CarryOS — çeviriler
   Türkçe metinler index.html içinde durur; burada İngilizce
   karşılıklar ve JS ile üretilen metinler yer alır.
   ========================================================== */
window.CARRY_I18N = {
  en: {
    "nav.why": "Idea", "nav.features": "Features", "nav.how": "Install", "nav.inside": "Inside the USB",
    "nav.compat": "Compatibility", "nav.faq": "FAQ", "nav.download": "Download",

    "ad.label": "Advertisement",
    "ab.chip": "Ad blocker detected",
    "ab.title": 'Please turn off your ad blocker <em class="serif grad">to continue.</em>',
    "ab.text": "CarryOS is free and open source. A few simple ads are what keep this site running. To keep using the site, disable your ad blocker for it or add it to your allow list.",
    "ab.s1": "Click your ad blocker's icon in the browser.",
    "ab.s2": "Choose “Pause” or “Allow” for this site.",
    "ab.s3": "Reload the page with the button below.",
    "ab.btn": "I turned it off, reload",
    "ab.note": "Ads sit quietly between the content. Thank you.",

    "hero.eyebrow": "Preview release · Based on Debian 13",
    "hero.title": '<span class="line"><span>Your computer,</span></span><span class="line"><span class="serif grad">in your pocket.</span></span>',
    "hero.lead": "CarryOS is a portable Linux that fits on a USB stick. Your encrypted home folder, desktop and apps come with you — boot it on any computer and it becomes yours.",
    "hero.cta1": "Download CarryOS", "hero.cta2": "View on GitHub",
    "hero.f1": "Base", "hero.f2": "Encrypted home", "hero.f3": "Desktop", "hero.scroll": "Scroll",

    "why.k": "Idea",
    "why.text": "Computers are temporary. Your desktop isn't. CarryOS encrypts your home folder and puts it in your pocket. Wherever you boot it, that machine becomes yours.",

    "feat.k": "Features",
    "feat.h": 'A tiny stick, <em class="serif grad">a complete</em> desktop.',
    "feat.sub": "Every part serves one idea: your data stays with you, stays safe, and is ready the moment you boot.",
    "c1.t": "Encrypted home folder",
    "c1.p": "Your files are encrypted on the stick with LUKS2 (argon2id). Without your password, the drive is nothing but meaningless data.",
    "c1.tag": "unlocked at boot",
    "c2.t": "One password, one wizard",
    "c2.p": "On first boot you pick a username and a password. That password becomes your account password and also protects your encrypted storage.",
    "c3.t": "Debian 13 base",
    "c3.p": "A rock-solid, mature foundation. Thousands of packages, one apt command away.",
    "c4.t": "MATE",
    "c4.p": "A familiar desktop known for its classic layout and light resource use.",
    "c5.t": "Travels with you",
    "c5.p": "Your settings, documents and installed programs stay on the stick. It doesn't use the host computer's disk.",
    "c6.t": "UEFI and legacy BIOS",
    "c6.p": "Ready for UEFI computers via GPT. Support for older BIOS machines is a work in progress.",
    "c6.tag": "BIOS · experimental",
    "c7.t": "Light browser, full package archive",
    "c7.p": "Web access out of the box with NetSurf. Need a fuller browser? Install one with apt.",

    "how.k": "Install",
    "how.h": 'In four steps, <em class="serif grad">in your pocket.</em>',
    "s1.t": "Download the image", "s1.p": "Download carryos.img and verify its SHA-256 checksum.",
    "s2.t": "Write it to a USB", "s2.p": "Use a stick of at least 16 GB. Write it with balenaEtcher, Rufus (DD mode) or dd.",
    "s3.t": "Boot from USB", "s3.p": "Open the boot menu at startup (F12, F10, Esc; Option on a Mac) and choose the stick.",
    "s4.t": "Finish the wizard", "s4.p": "Choose a username and password. Your encrypted storage is prepared and the login screen appears.",
    "code.t": "Linux / macOS", "code.copy": "Copy",
    "code.c1": "# verify the checksum", "code.c2": "# write to the stick (replace sdX with your device)",
    "code.warn": "<b>Careful:</b> replace /dev/sdX with your own USB device (check with lsblk). dd erases the entire target device.",

    "in.k": "Inside the USB",
    "in.h": 'How is the stick <em class="serif grad">divided?</em>',
    "in.sub": "Example layout on a 64 GB stick. The encrypted home takes all the remaining space. Tap a partition to see what it does.",

    "fb.k": "First boot",
    "fb.h": 'Type your password, <em class="serif grad">the rest is automatic.</em>',
    "fb.p": "The wizard helps you get online, sets up your account and creates the encrypted storage with your password. From then on you sign in with the same password.",
    "fb.note": "The flow on the right is a simplified illustration, not the actual wizard screen.",

    "co.k": "Compatibility",
    "co.h": 'Where does it <em class="serif grad">run?</em>',
    "co.a": "Architecture", "co.ok": "Supported", "co.uefi": "Modern computers", "co.bios": "Older computers",
    "co.exp": "Experimental", "co.plan": "In progress", "co.net": "Network", "co.netv": "NetworkManager · Wi-Fi and wired",
    "co.usb": "Storage", "co.usbv": "16 GB or more · USB 3.0 recommended", "co.rec": "Recommended",
    "co.note": "Hardware varies enormously; we can't guarantee anything before you try it on your own machine. If you hit a problem, report it on GitHub.",

    "faq.k": "FAQ",
    "faq.h": 'Things people <em class="serif grad">ask.</em>',
    "q1.q": "Will it harm my computer's disk?",
    "q1.a": "CarryOS boots from the USB and installs itself onto the USB; it doesn't use the main disk. Still, pick the right device when writing the image: writing erases the entire target device.",
    "q2.q": "What if I forget my password?",
    "q2.a": "The encrypted home folder can't be opened without the password — that's the whole point of encryption. Keep separate backups of anything important.",
    "q3.q": "Which USB stick should I get?",
    "q3.a": "At least 16 GB, preferably USB 3.0 or faster. On sticks with slow write speeds, writing the image and the first setup can take a long time.",
    "q4.q": "Will it boot on every computer?",
    "q4.a": "It's meant to boot on most 64-bit UEFI computers. Older BIOS machines and some Macs may behave differently; see the Compatibility section.",
    "q5.q": "How do I update it or install new programs?",
    "q5.a": "It's Debian-based, so <code>sudo apt update &amp;&amp; sudo apt upgrade</code> in a terminal is enough. For new programs use <code>sudo apt install</code>.",
    "q6.q": "Where are the license and source code?",
    "q6.a": "Everything is in the GitHub repository. Use the GitHub button above to get there.",

    "dl.k": "Download",
    "dl.h": 'Put it in your <em class="serif grad">pocket.</em>',
    "dl.v": "Version", "dl.s": "Size", "dl.a": "Architecture",
    "ft.tag": "Your computer, in your pocket.", "ft.rel": "Release notes"
  },

  /* ---- JS ile üretilen içerikler ---- */
  dyn: {
    tr: {
      copy: "Kopyala", copied: "Kopyalandı ✓",
      files: ["~/belgeler/tez.odt", "~/fotoğraflar/2026/", "~/.ssh/id_ed25519", "~/projeler/carryos/", "~/.config/mate/"],
      usb: [
        { n: "bios_grub", s: "1 MB · ham", p: "Eski BIOS'lu bilgisayarlarda GRUB'un çekirdeği burada durur. UEFI'de kullanılmaz." },
        { n: "EFI (ESP)", s: "512 MB · FAT32", p: "UEFI'li bilgisayarların okuduğu önyükleme bölümü. Açılışı buradaki dosyalar başlatır." },
        { n: "Sistem", s: "≈ 13,5 GB · ext4", p: "Debian 13 ve MATE masaüstü burada yaşar. apt ile kurduğun programlar da bu bölüme yazılır." },
        { n: "Şifreli ev", s: "kalan alan · LUKS2 + ext4", p: "Belgelerin, fotoğrafların, ayarların. İlk açılışta sihirbaz belleğin kalan alanından oluşturur; şifren olmadan açılamaz." }
      ],
      term: [
        { t: "cmd", x: "carryos-firstboot" },
        { t: "ok", x: "Ağ bağlantısı bulundu (Wi-Fi)" },
        { t: "ask", x: "Kullanıcı adı ›", v: "kullanici" },
        { t: "ask", x: "Şifre ›", v: "••••••••••" },
        { t: "out", x: "Depolama alanın oluşturuluyor…" },
        { t: "bar" },
        { t: "ok", x: "Şifreli ev hazır  →  /home" },
        { t: "ok", x: "Hesap oluşturuldu" },
        { t: "d", x: "Giriş ekranına geçiliyor…" }
      ]
    },
    en: {
      copy: "Copy", copied: "Copied ✓",
      files: ["~/documents/thesis.odt", "~/photos/2026/", "~/.ssh/id_ed25519", "~/projects/carryos/", "~/.config/mate/"],
      usb: [
        { n: "bios_grub", s: "1 MB · raw", p: "On older BIOS computers, GRUB's core image lives here. Not used on UEFI." },
        { n: "EFI (ESP)", s: "512 MB · FAT32", p: "The boot partition UEFI computers read. The files here start the boot process." },
        { n: "System", s: "≈ 13.5 GB · ext4", p: "Debian 13 and the MATE desktop live here. Programs you install with apt are written to this partition too." },
        { n: "Encrypted home", s: "remaining space · LUKS2 + ext4", p: "Your documents, photos, settings. The wizard creates it from the rest of the stick on first boot; it can't be opened without your password." }
      ],
      term: [
        { t: "cmd", x: "carryos-firstboot" },
        { t: "ok", x: "Network found (Wi-Fi)" },
        { t: "ask", x: "Username ›", v: "user" },
        { t: "ask", x: "Password ›", v: "••••••••••" },
        { t: "out", x: "Creating your storage…" },
        { t: "bar" },
        { t: "ok", x: "Encrypted home ready  →  /home" },
        { t: "ok", x: "Account created" },
        { t: "d", x: "Switching to the login screen…" }
      ]
    }
  },
  meta: {
    tr: { title: "CarryOS — Bilgisayarın, cebinde.", desc: "CarryOS: bir USB belleğe sığan, şifreli ev dizinli, Debian 13 tabanlı taşınabilir Linux. Tak, aç, kendi masaüstünü kullan." },
    en: { title: "CarryOS — Your computer, in your pocket.", desc: "CarryOS: a portable, Debian 13-based Linux with an encrypted home folder that fits on a USB stick. Plug in, boot, use your own desktop." }
  }
};
