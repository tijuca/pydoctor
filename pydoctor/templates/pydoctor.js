function initPrivate() {
    var params = (new URL(document.location)).searchParams;
    if (!params || !parseInt(params.get('private'))) {
        document.body.classList.add("private-hidden");
    }
    updatePrivate();
}
function togglePrivate() {
    document.body.classList.toggle("private-hidden");
    updatePrivate();
}
function updatePrivate() {
    var hidden = document.body.classList.contains('private-hidden');
    document.querySelector('#showPrivate button').innerText =
        hidden ? 'Show Private API' : 'Hide Private API';
    if (history) {
        var search = hidden ? document.location.pathname : '?private=1';
        history.replaceState(null, '', search + document.location.hash);
    }
}
initPrivate();
