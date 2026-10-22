const en = {
  marketSellHint: 'Sell the entire holding at market', submitSell: 'Submit sell',
  unitPrice: 'Unit price', holdingValue: 'Value', limitSell: 'Limit sell', moreActions: 'More position actions',
  entryProtection: 'Attach TP / SL', enabled: 'Enabled',
  entryProtectionHint: 'Applies to this new order after it fills. To protect an existing position, use TP / SL in its actions menu.',
  marketExitHint: 'Close the entire position at market', exitFilled: 'Exit filled',
  exitIncomplete: 'The close was only partially filled. {size} remains; position data is refreshing.',
  history: 'Position history',
  recent: 'Latest {count} closed positions',
  loading: 'Loading exchange positions',
  loadingOrders: 'Loading conditional orders',
  entry: 'Entry',
  exit: 'Exit',
  historyHint: 'Exchange account history includes strategy and manual trades. Running strategies may open positions again.',
  historyUnsupported: 'Exchange position history is not available for this market yet.',
  historyFailed: 'Could not load position history. Please retry.',
  netPnl: 'Net PnL',
  grossPnl: 'Trading PnL',
  funding: 'Funding',
  opened: 'Opened / average price',
  closed: 'Closed / average price',
  quantity: 'Closed quantity',
  fees: 'Total fees',
  limitClose: 'Limit close',
  protection: 'TP / SL',
  addProtection: 'Add conditional exit',
  protectionHint: 'Mark-price trigger, then reduce-only market exit. Existing triggers appear in Open orders; cancel them before replacing.',
  triggerPrice: 'Trigger price',
  submitExit: 'Submit exit',
  orderAccepted: 'Exit order submitted. Fill and position status will refresh automatically.',
  protectionAccepted: 'Conditional exit submitted',
  invalidExitPrice: 'Check the exit price. TP must be on the profit side of the mark price, SL on the opposite side.',
  invalidContext: 'Select an account and instrument first.',
  positionChanged: 'Position changed. Refresh and retry.',
  protectionUnsupported: 'Manage existing-position TP/SL on the exchange for this venue.',
  protectionFailed: 'Could not update conditional orders. Refresh and check the exchange before retrying.',
  orderGone: 'Order is no longer open. Refresh and retry.',
  refresh: 'Refresh',
  empty: 'No closed positions',
  cancel: 'Cancel',
  nativeOrders: 'Conditional exits',
  retry: 'Retry',
  strategyConflict: 'Strategy {id} is actively managing this account and market. Quick Trade is paused to prevent the strategy from immediately changing or closing a manual position.',
  executionBusy: 'Another order is updating this position. Wait for reconciliation and retry.'
}
const zh = {
  marketSellHint: '按市价全部卖出', submitSell: '提交卖出',
  unitPrice: '单价', holdingValue: '价值', limitSell: '限价卖出', moreActions: '更多持仓操作',
  entryProtection: '开仓附带止盈止损', enabled: '已启用',
  entryProtectionHint: '仅用于本次新开仓，成交后提交止盈止损。已有持仓请在该持仓的操作菜单中设置。',
  marketExitHint: '按市价全部平仓', exitFilled: '平仓已成交',
  exitIncomplete: '本次平仓仅部分成交，仍剩余 {size}；正在刷新持仓。',
  history: '历史仓位',
  recent: '最近 {count} 笔已平仓',
  loading: '正在读取交易所仓位',
  loadingOrders: '正在读取止盈止损委托',
  entry: '开仓',
  exit: '平仓',
  historyHint: '交易所账户历史包含策略与手动交易；运行中的策略可能重新开仓。',
  historyUnsupported: '当前市场暂不支持读取交易所历史仓位。',
  historyFailed: '历史仓位读取失败，请重试。',
  netPnl: '净盈亏', grossPnl: '交易盈亏', funding: '资金费用',
  opened: '开仓时间 / 均价', closed: '平仓时间 / 均价', quantity: '平仓数量', fees: '总手续费',
  limitClose: '限价平仓', protection: '止盈止损', addProtection: '添加止盈止损',
  protectionHint: '按标记价触发后市价减仓。已有条件单在当前委托中查看，修改前请先撤销原单。',
  triggerPrice: '触发价格', submitExit: '提交平仓',
  orderAccepted: '平仓委托已提交，成交及持仓状态将自动刷新。',
  protectionAccepted: '止盈止损委托已提交',
  invalidExitPrice: '请检查价格：止盈应在标记价的盈利方向，止损在相反方向。',
  invalidContext: '请先选择账户和交易对。', positionChanged: '持仓已变化，请刷新后重试。',
  protectionUnsupported: '该交易所的已有持仓止盈止损请前往交易所管理。',
  protectionFailed: '条件单操作失败，请刷新并核对交易所后再重试。',
  orderGone: '该委托已不在挂单中，请刷新。', refresh: '刷新', empty: '暂无已平仓仓位',
  cancel: '取消', nativeOrders: '止盈止损委托', retry: '重试',
  strategyConflict: '策略 {id} 正在接管这个账户和交易对。闪电交易已暂停，避免手动仓位被策略立即调整或平仓。',
  executionBusy: '另一笔委托正在更新该仓位，请等待对账完成后重试。'
}
const tw = { ...zh, marketSellHint: '按市價全部賣出', submitSell: '提交賣出', unitPrice: '單價', holdingValue: '價值', limitSell: '限價賣出', moreActions: '更多持倉操作', entryProtection: '開倉附帶止盈止損', enabled: '已啟用', entryProtectionHint: '僅用於本次新開倉，成交後提交止盈止損。已有持倉請在該持倉的操作選單中設定。', marketExitHint: '按市價全部平倉', exitFilled: '平倉已成交', exitIncomplete: '本次平倉僅部分成交，仍剩餘 {size}；正在刷新持倉。', history: '歷史倉位', historyHint: '交易所帳戶歷史包含策略與手動交易；運行中的策略可能重新開倉。', historyUnsupported: '當前市場暫不支援讀取交易所歷史倉位。', historyFailed: '歷史倉位讀取失敗，請重試。', netPnl: '淨盈虧', grossPnl: '交易盈虧', funding: '資金費用', opened: '開倉時間 / 均價', closed: '平倉時間 / 均價', quantity: '平倉數量', fees: '總手續費', limitClose: '限價平倉', protection: '止盈止損', addProtection: '添加止盈止損', protectionHint: '按標記價觸發後市價減倉。已有條件單在當前委託中查看，修改前請先撤銷原單。', triggerPrice: '觸發價格', submitExit: '提交平倉', orderAccepted: '平倉委託已提交，成交及持倉狀態將自動刷新。', protectionAccepted: '止盈止損委託已提交', invalidExitPrice: '請檢查價格：止盈應在標記價的盈利方向，止損在相反方向。', invalidContext: '請先選擇帳戶和交易對。', positionChanged: '持倉已變化，請刷新後重試。', protectionUnsupported: '該交易所的已有持倉止盈止損請前往交易所管理。', protectionFailed: '條件單操作失敗，請刷新並核對交易所後再重試。', orderGone: '該委託已不在掛單中，請刷新。', empty: '暫無已平倉倉位', nativeOrders: '止盈止損委託', retry: '重試', strategyConflict: '策略 {id} 正在接管這個帳戶和交易對。閃電交易已暫停，避免手動倉位被策略立即調整或平倉。', executionBusy: '另一筆委託正在更新此倉位，請等待對帳完成後重試。' }
const localizedExecution = {
  'de-DE': {
    exitIncomplete: 'Die Position wurde nur teilweise geschlossen. {size} verbleibt; die Positionsdaten werden aktualisiert.',
    executionBusy: 'Eine andere Order aktualisiert diese Position. Warten Sie auf den Abgleich und versuchen Sie es erneut.'
  },
  'fr-FR': {
    exitIncomplete: 'La clôture n’a été exécutée que partiellement. Il reste {size} ; les données de position sont en cours d’actualisation.',
    executionBusy: 'Un autre ordre met à jour cette position. Attendez la fin du rapprochement avant de réessayer.'
  },
  'ja-JP': {
    exitIncomplete: '決済は一部のみ約定しました。残りは {size} です。ポジション情報を更新しています。',
    executionBusy: '別の注文がこのポジションを更新しています。照合が完了してから再試行してください。'
  },
  'ko-KR': {
    exitIncomplete: '포지션이 일부만 종료되었습니다. {size}이(가) 남아 있으며 포지션 정보를 새로고침하고 있습니다.',
    executionBusy: '다른 주문이 이 포지션을 업데이트하고 있습니다. 대사가 완료된 후 다시 시도하세요.'
  },
  'ru-RU': {
    exitIncomplete: 'Позиция закрыта лишь частично. Осталось {size}; данные позиции обновляются.',
    executionBusy: 'Другой ордер обновляет эту позицию. Дождитесь сверки и повторите попытку.'
  },
  'th-TH': {
    exitIncomplete: 'ปิดสถานะได้เพียงบางส่วน ยังเหลือ {size} และกำลังรีเฟรชข้อมูลสถานะ',
    executionBusy: 'มีคำสั่งอื่นกำลังอัปเดตสถานะนี้ โปรดรอให้การกระทบยอดเสร็จแล้วลองอีกครั้ง'
  },
  'vi-VN': {
    exitIncomplete: 'Vị thế chỉ được đóng một phần. Còn lại {size}; dữ liệu vị thế đang được làm mới.',
    executionBusy: 'Một lệnh khác đang cập nhật vị thế này. Hãy chờ đối soát hoàn tất rồi thử lại.'
  },
  'ar-SA': {
    exitIncomplete: 'تم إغلاق المركز جزئيًا فقط. المتبقي {size}؛ جارٍ تحديث بيانات المركز.',
    executionBusy: 'هناك أمر آخر يحدّث هذا المركز. انتظر اكتمال التسوية ثم أعد المحاولة.'
  }
}
const prefix = values => Object.fromEntries(Object.entries(values).map(([key, value]) => [`quickTrade.workflow.${key}`, value]))
export default Object.fromEntries(['en-US', 'zh-CN', 'zh-TW', 'de-DE', 'fr-FR', 'ja-JP', 'ko-KR', 'ru-RU', 'th-TH', 'vi-VN', 'ar-SA'].map(lang => [lang, prefix(lang === 'zh-CN' ? zh : lang === 'zh-TW' ? tw : { ...en, ...(localizedExecution[lang] || {}) })]))
