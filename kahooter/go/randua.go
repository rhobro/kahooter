package main

import (
	"github.com/rhobro/goutils/pkg/httputil"
	"fmt"
)

func main() {
	fmt.Println(httputil.RandUA())
}
