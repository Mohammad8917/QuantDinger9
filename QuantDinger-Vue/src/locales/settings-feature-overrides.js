const en = {
  'settings.group.features': 'Product features',
  'settings.field.BILLING_ENABLED': 'Billing and credits',
  'settings.desc.BILLING_ENABLED': 'Show credits, recharge, membership and billing settings. When disabled, metered features do not charge credits.',
  'settings.field.MARKETPLACE_ENABLED': 'Marketplace',
  'settings.desc.MARKETPLACE_ENABLED': 'Show the marketplace and publishing actions. Disable this for private or team-only deployments.',
  'settings.field.ENABLE_REGISTRATION': 'Public registration',
  'settings.desc.ENABLE_REGISTRATION': 'Allow visitors to create accounts. Disable this for a closed team deployment.',
  'settings.field.AGENT_LIVE_TRADING_ENABLED': 'Allow Agent live trading',
  'settings.desc.AGENT_LIVE_TRADING_ENABLED': 'Global safety switch for real orders submitted with Agent tokens. Paper trading remains available when disabled.',
  'settings.field.QUANTDINGER_DEPLOYMENT_MODE': 'Deployment mode',
  'settings.desc.QUANTDINGER_DEPLOYMENT_MODE': 'Controls Agent token policy for self-hosted and multi-tenant deployments.',
  'settings.field.AGENT_JOBS_MAX_WORKERS': 'Agent job workers',
  'settings.desc.AGENT_JOBS_MAX_WORKERS': 'Maximum concurrent in-process Agent jobs. A restart is required after changing it.'
}

const messages = {
  'en-US': en,
  'zh-CN': {
    'settings.group.features': '产品功能开关',
    'settings.field.BILLING_ENABLED': '计费与积分',
    'settings.desc.BILLING_ENABLED': '显示积分、充值、会员和计费设置。关闭后，按量功能不再扣除积分。',
    'settings.field.MARKETPLACE_ENABLED': '策略与指标市场',
    'settings.desc.MARKETPLACE_ENABLED': '显示市场入口和发布操作。本地单机或内部团队部署可关闭。',
    'settings.field.ENABLE_REGISTRATION': '开放用户注册',
    'settings.desc.ENABLE_REGISTRATION': '允许访客创建账号。内部团队部署建议关闭。',
    'settings.field.AGENT_LIVE_TRADING_ENABLED': '允许 Agent 实盘交易',
    'settings.desc.AGENT_LIVE_TRADING_ENABLED': 'Agent 令牌提交真实订单的总安全开关。关闭后仍可进行模拟交易。',
    'settings.field.QUANTDINGER_DEPLOYMENT_MODE': '部署模式',
    'settings.desc.QUANTDINGER_DEPLOYMENT_MODE': '控制自托管与多租户环境中的 Agent 令牌策略。',
    'settings.field.AGENT_JOBS_MAX_WORKERS': 'Agent 任务并发数',
    'settings.desc.AGENT_JOBS_MAX_WORKERS': '进程内可同时执行的 Agent 任务上限，修改后需要重启服务。'
  },
  'zh-TW': {
    'settings.group.features': '產品功能開關',
    'settings.field.BILLING_ENABLED': '計費與積分',
    'settings.desc.BILLING_ENABLED': '顯示積分、儲值、會員與計費設定。關閉後，按量功能不再扣除積分。',
    'settings.field.MARKETPLACE_ENABLED': '策略與指標市場',
    'settings.desc.MARKETPLACE_ENABLED': '顯示市場入口與發布操作。本機或內部團隊部署可關閉。',
    'settings.field.ENABLE_REGISTRATION': '開放使用者註冊',
    'settings.desc.ENABLE_REGISTRATION': '允許訪客建立帳號。內部團隊部署建議關閉。'
  },
  'ja-JP': {
    'settings.group.features': '製品機能',
    'settings.field.BILLING_ENABLED': '課金とクレジット',
    'settings.desc.BILLING_ENABLED': 'クレジット、チャージ、会員機能、課金設定を表示します。無効時は従量機能でクレジットを消費しません。',
    'settings.field.MARKETPLACE_ENABLED': 'マーケットプレイス',
    'settings.desc.MARKETPLACE_ENABLED': 'マーケットと公開操作を表示します。個人または社内利用では無効にできます。',
    'settings.field.ENABLE_REGISTRATION': '公開ユーザー登録',
    'settings.desc.ENABLE_REGISTRATION': '訪問者によるアカウント作成を許可します。閉じたチームでは無効にしてください。'
  },
  'ko-KR': {
    'settings.group.features': '제품 기능',
    'settings.field.BILLING_ENABLED': '결제 및 크레딧',
    'settings.desc.BILLING_ENABLED': '크레딧, 충전, 멤버십 및 결제 설정을 표시합니다. 끄면 사용량 기반 기능에서 크레딧을 차감하지 않습니다.',
    'settings.field.MARKETPLACE_ENABLED': '마켓플레이스',
    'settings.desc.MARKETPLACE_ENABLED': '마켓과 게시 작업을 표시합니다. 개인 또는 내부 팀 배포에서는 끌 수 있습니다.',
    'settings.field.ENABLE_REGISTRATION': '공개 회원가입',
    'settings.desc.ENABLE_REGISTRATION': '방문자의 계정 생성을 허용합니다. 폐쇄형 팀에서는 끄는 것이 좋습니다.'
  },
  'de-DE': {
    'settings.group.features': 'Produktfunktionen',
    'settings.field.BILLING_ENABLED': 'Abrechnung und Guthaben',
    'settings.desc.BILLING_ENABLED': 'Zeigt Guthaben, Aufladung, Mitgliedschaften und Abrechnung. Bei Deaktivierung werden keine Guthabenpunkte berechnet.',
    'settings.field.MARKETPLACE_ENABLED': 'Marktplatz',
    'settings.desc.MARKETPLACE_ENABLED': 'Zeigt Marktplatz und Veröffentlichungsaktionen. Für private oder interne Installationen deaktivieren.',
    'settings.field.ENABLE_REGISTRATION': 'Öffentliche Registrierung',
    'settings.desc.ENABLE_REGISTRATION': 'Erlaubt Besuchern, Konten anzulegen. Für geschlossene Teams deaktivieren.'
  },
  'fr-FR': {
    'settings.group.features': 'Fonctions du produit',
    'settings.field.BILLING_ENABLED': 'Facturation et crédits',
    'settings.desc.BILLING_ENABLED': 'Affiche les crédits, la recharge, les abonnements et la facturation. Désactivé, aucun crédit n’est débité.',
    'settings.field.MARKETPLACE_ENABLED': 'Marché',
    'settings.desc.MARKETPLACE_ENABLED': 'Affiche le marché et les actions de publication. À désactiver pour un usage privé ou interne.',
    'settings.field.ENABLE_REGISTRATION': 'Inscription publique',
    'settings.desc.ENABLE_REGISTRATION': 'Autorise les visiteurs à créer un compte. À désactiver pour une équipe fermée.'
  },
  'ru-RU': {
    'settings.group.features': 'Функции продукта',
    'settings.field.BILLING_ENABLED': 'Оплата и кредиты',
    'settings.desc.BILLING_ENABLED': 'Показывает кредиты, пополнение, подписки и настройки оплаты. При отключении кредиты не списываются.',
    'settings.field.MARKETPLACE_ENABLED': 'Маркетплейс',
    'settings.desc.MARKETPLACE_ENABLED': 'Показывает маркетплейс и публикацию. Можно отключить для личной или внутренней установки.',
    'settings.field.ENABLE_REGISTRATION': 'Открытая регистрация',
    'settings.desc.ENABLE_REGISTRATION': 'Разрешает посетителям создавать аккаунты. Отключите для закрытой команды.'
  },
  'th-TH': {
    'settings.group.features': 'ฟีเจอร์ผลิตภัณฑ์',
    'settings.field.BILLING_ENABLED': 'การเรียกเก็บเงินและเครดิต',
    'settings.desc.BILLING_ENABLED': 'แสดงเครดิต การเติมเงิน สมาชิก และการตั้งค่าการเรียกเก็บเงิน เมื่อปิดจะไม่มีการหักเครดิต',
    'settings.field.MARKETPLACE_ENABLED': 'มาร์เก็ตเพลส',
    'settings.desc.MARKETPLACE_ENABLED': 'แสดงตลาดและการเผยแพร่ ปิดได้สำหรับการใช้งานส่วนตัวหรือภายในทีม',
    'settings.field.ENABLE_REGISTRATION': 'เปิดลงทะเบียนสาธารณะ',
    'settings.desc.ENABLE_REGISTRATION': 'อนุญาตให้ผู้เยี่ยมชมสร้างบัญชี ปิดสำหรับทีมแบบปิด'
  },
  'vi-VN': {
    'settings.group.features': 'Tính năng sản phẩm',
    'settings.field.BILLING_ENABLED': 'Thanh toán và tín dụng',
    'settings.desc.BILLING_ENABLED': 'Hiển thị tín dụng, nạp tiền, thành viên và cài đặt thanh toán. Khi tắt, tính năng theo mức dùng không trừ tín dụng.',
    'settings.field.MARKETPLACE_ENABLED': 'Chợ nội dung',
    'settings.desc.MARKETPLACE_ENABLED': 'Hiển thị chợ và thao tác xuất bản. Có thể tắt cho triển khai cá nhân hoặc nội bộ.',
    'settings.field.ENABLE_REGISTRATION': 'Đăng ký công khai',
    'settings.desc.ENABLE_REGISTRATION': 'Cho phép khách tạo tài khoản. Nên tắt cho nhóm nội bộ.'
  },
  'ar-SA': {
    'settings.group.features': 'ميزات المنتج',
    'settings.field.BILLING_ENABLED': 'الفوترة والرصيد',
    'settings.desc.BILLING_ENABLED': 'يعرض الرصيد والشحن والعضويات وإعدادات الفوترة. عند التعطيل لا يتم خصم الرصيد.',
    'settings.field.MARKETPLACE_ENABLED': 'السوق',
    'settings.desc.MARKETPLACE_ENABLED': 'يعرض السوق وإجراءات النشر. يمكن تعطيله للاستخدام الشخصي أو الداخلي.',
    'settings.field.ENABLE_REGISTRATION': 'التسجيل العام',
    'settings.desc.ENABLE_REGISTRATION': 'يسمح للزوار بإنشاء حسابات. عطّله لفرق العمل المغلقة.'
  }
}

export default messages
