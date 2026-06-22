param([string]$Title, [string]$Message, [string]$DiffPath)

Add-Type -AssemblyName System.Windows.Forms

if ($DiffPath -and (Test-Path $DiffPath)) {
    $encoded = [System.Uri]::EscapeDataString($DiffPath)
    $protocolUrl = "taskrunner://open?file=$encoded"

    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02
    )

    $textNodes = $template.GetElementsByTagName('text')
    $textNodes.Item(0).AppendChild($template.CreateTextNode($Title)) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode($Message)) | Out-Null

    $toastNode = $template.SelectSingleNode('//toast')
    $actions = $template.CreateElement('actions')
    $action = $template.CreateElement('action')
    $action.SetAttribute('content', '查看 Diff')
    $action.SetAttribute('arguments', $protocolUrl)
    $action.SetAttribute('activationType', 'protocol')
    $actions.AppendChild($action) | Out-Null
    $toastNode.AppendChild($actions) | Out-Null
    $toastNode.SetAttribute('launch', $protocolUrl)
    $toastNode.SetAttribute('activationType', 'protocol')

    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Task Runner')
    $notifier.Show($toast)
} else {
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipTitle = $Title
    $balloon.BalloonTipText = $Message
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(10000)
    Start-Sleep -Seconds 2
    $balloon.Dispose()
}
