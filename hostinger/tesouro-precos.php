<?php
// Espelho do CSV público "Preço e Taxa dos Títulos do Tesouro Direto" (Tesouro Transparente) para o pipeline do
// Comparador de Ativos. Os servidores do GitHub Actions recebem 429 (Too Many Requests) do Tesouro Transparente
// desde 20/10/2026; daqui da Hostinger o arquivo baixa normalmente.
// Busca só este endereço fixo (não é um proxy aberto), guarda a cópia por 6 horas e, se a origem falhar,
// continua servindo a última cópia boa.
declare(strict_types=1);
@set_time_limit(240);

$origem = 'https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv';
$copia = __DIR__ . '/tesouro-precos.cache.csv';
$validade = 6 * 3600;

function valido(string $arq): bool {
    if (!is_file($arq) || filesize($arq) < 200000) return false;
    $h = fopen($arq, 'rb');
    $ini = (string) fread($h, 400);
    fclose($h);
    return strpos($ini, 'Tipo Titulo') !== false;
}

clearstatcache();
if (!valido($copia) || time() - filemtime($copia) > $validade) {
    $tmp = $copia . '.tmp';
    $fp = fopen($tmp, 'wb');
    if ($fp !== false) {
        $ch = curl_init($origem);
        curl_setopt_array($ch, [
            CURLOPT_FILE => $fp,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_CONNECTTIMEOUT => 20,
            CURLOPT_TIMEOUT => 180,
            CURLOPT_FAILONERROR => true,
            CURLOPT_USERAGENT => 'Mozilla/5.0 (compatible; MaisonHub-Comparador/1.0; +https://hubmaison.com/comparadordeativos/)',
        ]);
        $ok = curl_exec($ch);
        $codigo = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        fclose($fp);
        clearstatcache();
        if ($ok && $codigo === 200 && valido($tmp)) {
            rename($tmp, $copia);
        } else {
            @unlink($tmp);
        }
    }
}

clearstatcache();
if (!valido($copia)) {
    http_response_code(503);
    header('Retry-After: 600');
    header('Content-Type: text/plain; charset=utf-8');
    echo "Cópia indisponível no momento.";
    exit;
}
header('Content-Type: text/csv; charset=ISO-8859-1');
header('Cache-Control: no-store, max-age=0');
header('X-Robots-Tag: noindex');
header('Last-Modified: ' . gmdate('D, d M Y H:i:s', filemtime($copia)) . ' GMT');
header('Content-Length: ' . filesize($copia));
readfile($copia);
