$ErrorActionPreference = 'Stop'

$signature = @'
[DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
public static extern int LCMapStringEx(
    string lpLocaleName,
    uint dwMapFlags,
    string lpSrcStr,
    int cchSrc,
    StringBuilder lpDestStr,
    int cchDest,
    IntPtr lpVersionInformation,
    IntPtr lpReserved,
    IntPtr sortHandle
);
'@

Add-Type -MemberDefinition $signature -Name LocaleMap -Namespace QuantDinger -UsingNamespace System.Text

function Convert-ToTraditionalChinese([string] $value) {
  if ([string]::IsNullOrEmpty($value)) {
    return $value
  }

  $buffer = [System.Text.StringBuilder]::new($value.Length * 2 + 8)
  $length = [QuantDinger.LocaleMap]::LCMapStringEx(
    'zh-Hant',
    0x04000000,
    $value,
    $value.Length,
    $buffer,
    $buffer.Capacity,
    [IntPtr]::Zero,
    [IntPtr]::Zero,
    [IntPtr]::Zero
  )
  if ($length -le 0) {
    throw "Traditional Chinese conversion failed."
  }

  $converted = $buffer.ToString().Substring(0, $length)
  $replacements = [ordered]@{
    '賬戶' = '帳戶'
    '軟件' = '軟體'
    '數據' = '資料'
    '信息' = '資訊'
    '保存' = '儲存'
    '默認' = '預設'
    '配置' = '設定'
    '加載' = '載入'
    '服務器' = '伺服器'
    '代碼' = '程式碼'
    '鏈接' = '連結'
    '打印' = '列印'
    '視頻' = '影片'
    '網絡' = '網路'
    '文件' = '檔案'
    '添加' = '新增'
    '創建' = '建立'
    '當前' = '目前'
    '通過' = '透過'
    '支持' = '支援'
    '用戶' = '使用者'
    '鼠標' = '滑鼠'
    '接口' = '介面'
    '程序' = '程式'
    '組件' = '元件'
    '這里' = '這裡'
    '里' = '裡'
    '然后' = '然後'
    '并' = '並'
    '沖突' = '衝突'
    '質量' = '品質'
    '置信度' = '信心程度'
    '隊列' = '佇列'
    '后' = '後'
    '用于' = '用於'
    '周期' = '週期'
    '運行' = '執行'
    '源碼' = '原始碼'
    '高級' = '進階'
    '余量' = '餘量'
    '復制' = '複製'
    '應用' = '套用'
    '字段' = '欄位'
    '范圍' = '範圍'
    '杠桿' = '槓桿'
    '調用' = '呼叫'
    '登錄' = '登入'
    '發布' = '發佈'
    '單個' = '單一'
    '主干' = '主幹'
    '標識' = '識別碼'
    '示例' = '範例'
    '響應' = '反應'
  }
  foreach ($replacement in $replacements.GetEnumerator()) {
    $converted = $converted.Replace($replacement.Key, $replacement.Value)
  }
  return $converted
}

function Read-LiteralMessages([string] $source, [int] $startIndex = 0) {
  $messages = [ordered]@{}
  $pattern = '("(?:[^"\\]|\\.)*")\s*:\s*("(?:[^"\\]|\\.)*")'
  foreach ($match in [regex]::Matches($source.Substring($startIndex), $pattern)) {
    $pair = ConvertFrom-Json "[$($match.Groups[1].Value),$($match.Groups[2].Value)]"
    $messages[$pair[0]] = $pair[1]
  }
  return $messages
}

$root = Split-Path -Parent $PSScriptRoot
$zhCnPath = Join-Path $root 'src/locales/lang/zh-CN.js'
$zhTwPath = Join-Path $root 'src/locales/lang/zh-TW.js'
$outputPath = Join-Path $root 'src/locales/zh-tw-product-overrides.js'
$zhCnSource = [IO.File]::ReadAllText($zhCnPath)
$zhTwSource = [IO.File]::ReadAllText($zhTwPath)
$exportStart = $zhCnSource.IndexOf('export default {')
if ($exportStart -lt 0) {
  throw 'The Simplified Chinese locale has no default export.'
}

$zhCnMessages = Read-LiteralMessages $zhCnSource $exportStart
$zhTwMessages = Read-LiteralMessages $zhTwSource
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('const messages = {')
$lines.Add("  'zh-TW': {")

$entries = foreach ($key in ($zhCnMessages.Keys | Sort-Object)) {
  if ($zhTwMessages.Contains($key)) {
    continue
  }
  [PSCustomObject]@{
    Key = $key
    Value = Convert-ToTraditionalChinese ([string] $zhCnMessages[$key])
  }
}

for ($index = 0; $index -lt $entries.Count; $index += 1) {
  $keyJson = ConvertTo-Json $entries[$index].Key -Compress
  $valueJson = ConvertTo-Json $entries[$index].Value -Compress
  $comma = if ($index -lt $entries.Count - 1) { ',' } else { '' }
  $lines.Add(('    {0}: {1}{2}' -f $keyJson, $valueJson, $comma))
}

$lines.Add('  }')
$lines.Add('}')
$lines.Add('')
$lines.Add('export default messages')
$lines.Add('')
[IO.File]::WriteAllText($outputPath, ($lines -join "`n"), [Text.UTF8Encoding]::new($false))
Write-Output "Wrote $($entries.Count) Traditional Chinese overrides to $outputPath"
