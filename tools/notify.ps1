# Shows a Windows notification. Used by tools\twice_daily.py.
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\notify.ps1 -Title "..." -Text "..."
param([string]$Title = "Attention Span", [string]$Text = "")
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $xml.GetElementsByTagName("text")
$nodes.Item(0).AppendChild($xml.CreateTextNode($Title)) | Out-Null
$nodes.Item(1).AppendChild($xml.CreateTextNode($Text)) | Out-Null
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
