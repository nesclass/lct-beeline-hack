<script>
  import { go } from '../lib/router.svelte.js';
  let { href, disabled = false, children, ...rest } = $props();
  function click(e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    if (!disabled) go(href);
  }
</script>

<a {href} onclick={click} aria-disabled={disabled || undefined} {...rest}>{@render children()}</a>
