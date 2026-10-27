// Tiny doubly-linked navigation history. React Navigation still owns the real
// stack; this structure gives the app an explicit back/forward model without
// coupling screens to each other.
export class PageNode {
  constructor(name, params) {
    this.name = name;
    this.params = params;
    this.prev = null;
    this.next = null;
  }
}

export class PageHistory {
  constructor() {
    this.current = null;
  }

  visit(name, params) {
    const node = new PageNode(name, params);
    if (this.current) {
      this.current.next = node;
      node.prev = this.current;
    }
    this.current = node;
    return node;
  }

  back() {
    if (!this.current?.prev) return null;
    this.current = this.current.prev;
    return this.current;
  }

  forward() {
    if (!this.current?.next) return null;
    this.current = this.current.next;
    return this.current;
  }

  reset(name, params) {
    this.current = new PageNode(name, params);
    return this.current;
  }
}
