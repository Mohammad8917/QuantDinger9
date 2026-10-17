const en = {
  'backtestWorkbench.strategy': 'Strategy',
  'backtestWorkbench.period': 'Research period',
  'backtestWorkbench.capital': 'Initial capital',
  'backtestWorkbench.factor': 'Research factor',
  'backtestWorkbench.advancedSettings': 'Advanced settings',
  'backtestWorkbench.hideSettings': 'Hide settings',
  'backtestWorkbench.stage.running': 'Starting research job',
  'backtestWorkbench.stage.preparing': 'Validating strategy contract',
  'backtestWorkbench.stage.loading_market_data': 'Loading and aligning market data',
  'backtestWorkbench.stage.preparing_simulation': 'Preparing execution model',
  'backtestWorkbench.stage.running_simulation': 'Replaying orders and positions',
  'backtestWorkbench.stage.building_report': 'Building risk and performance report',
  'backtestWorkbench.stage.persisting_result': 'Saving the audited result',
  'backtestWorkbench.stage.completed': 'Backtest complete',
  'backtestWorkbench.stage.succeeded': 'Backtest complete'
}

const zhCN = {
  'backtestWorkbench.strategy': '策略',
  'backtestWorkbench.period': '研究区间',
  'backtestWorkbench.capital': '初始资金',
  'backtestWorkbench.factor': '研究因子',
  'backtestWorkbench.advancedSettings': '高级设置',
  'backtestWorkbench.hideSettings': '收起设置',
  'backtestWorkbench.stage.running': '正在启动研究任务',
  'backtestWorkbench.stage.preparing': '正在校验策略契约',
  'backtestWorkbench.stage.loading_market_data': '正在加载并对齐行情数据',
  'backtestWorkbench.stage.preparing_simulation': '正在准备成交模型',
  'backtestWorkbench.stage.running_simulation': '正在逐根回放订单与持仓',
  'backtestWorkbench.stage.building_report': '正在生成收益与风险报告',
  'backtestWorkbench.stage.persisting_result': '正在保存审计结果',
  'backtestWorkbench.stage.completed': '回测已完成',
  'backtestWorkbench.stage.succeeded': '回测已完成'
}

const zhTW = {
  'backtestWorkbench.strategy': '策略',
  'backtestWorkbench.period': '研究區間',
  'backtestWorkbench.capital': '初始資金',
  'backtestWorkbench.factor': '研究因子',
  'backtestWorkbench.advancedSettings': '進階設定',
  'backtestWorkbench.hideSettings': '收起設定',
  'backtestWorkbench.stage.running': '正在啟動研究任務',
  'backtestWorkbench.stage.preparing': '正在驗證策略契約',
  'backtestWorkbench.stage.loading_market_data': '正在載入並對齊行情資料',
  'backtestWorkbench.stage.preparing_simulation': '正在準備成交模型',
  'backtestWorkbench.stage.running_simulation': '正在逐根回放訂單與持倉',
  'backtestWorkbench.stage.building_report': '正在產生收益與風險報告',
  'backtestWorkbench.stage.persisting_result': '正在儲存稽核結果',
  'backtestWorkbench.stage.completed': '回測已完成',
  'backtestWorkbench.stage.succeeded': '回測已完成'
}

const messages = {
  'en-US': en,
  'zh-CN': zhCN,
  'zh-TW': zhTW
}

;['ar-SA', 'de-DE', 'fr-FR', 'ja-JP', 'ko-KR', 'ru-RU', 'th-TH', 'vi-VN'].forEach(code => { messages[code] = { ...en } })

export default messages
